# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
from cocotb.types import Logic
from cocotb.types import LogicArray

async def await_half_sclk(dut):
    """Wait for the SCLK signal to go high or low."""
    start_time = cocotb.utils.get_sim_time(units="ns")
    while True:
        await ClockCycles(dut.clk, 1)
        if (start_time + 100*100*0.5) < cocotb.utils.get_sim_time(units="ns"):
            break
    return

def ui_in_logicarray(ncs, bit, sclk):
    """Setup the ui_in value as a LogicArray."""
    return LogicArray(f"00000{ncs}{bit}{sclk}")

async def send_spi_transaction(dut, r_w, address, data):
    """
    Send an SPI transaction with format:
    - 1 bit for Read/Write
    - 7 bits for address
    - 8 bits for data
    """
    if isinstance(data, LogicArray):
        data_int = int(data)
    else:
        data_int = data
    if address < 0 or address > 127:
        raise ValueError("Address must be 7-bit (0-127)")
    if data_int < 0 or data_int > 255:
        raise ValueError("Data must be 8-bit (0-255)")
    
    first_byte = (int(r_w) << 7) | address
    sclk = 0
    ncs = 0
    bit = 0
    dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
    await ClockCycles(dut.clk, 1)

    for i in range(8):
        bit = (first_byte >> (7-i)) & 0x1
        sclk = 0
        dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
        await await_half_sclk(dut)
        sclk = 1
        dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
        await await_half_sclk(dut)

    for i in range(8):
        bit = (data_int >> (7-i)) & 0x1
        sclk = 0
        dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
        await await_half_sclk(dut)
        sclk = 1
        dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
        await await_half_sclk(dut)
    
    sclk = 0
    ncs = 1
    bit = 0
    dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
    await ClockCycles(dut.clk, 600)
    return ui_in_logicarray(ncs, bit, sclk)

async def measure_freq(dut, timeout_ns=3_000_000):
    """Measures the period of the PWM signal on uo_out[0] using manual polling."""
    start_time = cocotb.utils.get_sim_time(units="ns")
    
    # Wait for the signal to be low
    while dut.uo_out[0].value == 1:
        await ClockCycles(dut.clk, 1)
        if cocotb.utils.get_sim_time(units="ns") - start_time > timeout_ns: return 0
    
    # Wait for a rising edge
    while dut.uo_out[0].value == 0:
        await ClockCycles(dut.clk, 1)
        if cocotb.utils.get_sim_time(units="ns") - start_time > timeout_ns: return 0
    
    t_rise1 = cocotb.utils.get_sim_time(units="ns")

    # Wait for a falling edge
    while dut.uo_out[0].value == 1:
        await ClockCycles(dut.clk, 1)
        if cocotb.utils.get_sim_time(units="ns") - start_time > timeout_ns: return 0

    # Wait for the next rising edge
    while dut.uo_out[0].value == 0:
        await ClockCycles(dut.clk, 1)
        if cocotb.utils.get_sim_time(units="ns") - start_time > timeout_ns: return 0
        
    t_rise2 = cocotb.utils.get_sim_time(units="ns")
    return t_rise2 - t_rise1

@cocotb.test()
async def test_pwm_freq(dut):
    dut._log.info("Start PWM frequency test")
    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    dut._log.info("Reset")
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    # Configure PWM for 50% duty cycle
    await send_spi_transaction(dut, 1, 0x00, 0xFF) # Enable all uo_out
    await send_spi_transaction(dut, 1, 0x02, 0xFF) # Enable PWM on all uo_out
    await send_spi_transaction(dut, 1, 0x04, 0x80) # Set duty cycle ~50%

    period_ns = await measure_freq(dut)
    assert period_ns > 0, "Timeout while measuring frequency."
    
    frequency = 1 / (period_ns * 1e-9)
    dut._log.info(f"Measured frequency: {frequency:.2f} Hz")

    expected_freq = 3000
    tolerance = 0.01 # 1%
    assert expected_freq * (1 - tolerance) <= frequency <= expected_freq * (1 + tolerance), \
        f"Frequency {frequency:.2f} Hz is out of tolerance range."

    dut._log.info("PWM Frequency test completed successfully")

async def test_duty_cycle(dut, duty_fraction):
    """Helper to set and verify a duty cycle."""
    duty_value = int(duty_fraction * 255)
    dut._log.info(f"----- Verifying Duty Cycle: {duty_fraction*100:.0f}% (Value: {duty_value}) -----")
    await send_spi_transaction(dut, 1, 0x04, duty_value)
    
    # Wait for the change to propagate over a few cycles
    await ClockCycles(dut.clk, 35000)
    
    # --- Measure Period ---
    period_ns = await measure_freq(dut)
    
    # Handle edge cases (0% or 100%)
    if period_ns == 0:
        measured_duty = 0.0 if dut.uo_out[0].value == 0 else 1.0
        dut._log.info(f"Signal is static. Measured duty: {measured_duty*100:.0f}%")
        assert abs(measured_duty - duty_fraction) < 0.01, "Static duty cycle is incorrect."
        return

    # --- Measure High Time ---
    start_time = cocotb.utils.get_sim_time(units="ns")
    timeout_ns = period_ns * 2 # Set timeout relative to period
    
    # Find rising edge
    while dut.uo_out[0].value == 0: await ClockCycles(dut.clk, 1)
    t_rise = cocotb.utils.get_sim_time(units="ns")
    
    # Find falling edge
    while dut.uo_out[0].value == 1: await ClockCycles(dut.clk, 1)
    t_fall = cocotb.utils.get_sim_time(units="ns")
        
    high_time_ns = t_fall - t_rise
    measured_duty = high_time_ns / period_ns
    
    dut._log.info(f"Measured duty: {measured_duty*100:.2f}%")
    tolerance = 0.02 # 2% tolerance
    assert abs(measured_duty - duty_fraction) < tolerance, \
        f"Measured duty {measured_duty*100:.2f}% is out of tolerance for expected {duty_fraction*100:.2f}%"

@cocotb.test()
async def test_pwm_duty(dut):
    dut._log.info("Start PWM Duty Cycle test suite")
    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    dut._log.info("Reset")
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    # Configure PWM
    await send_spi_transaction(dut, 1, 0x00, 0xFF)
    await send_spi_transaction(dut, 1, 0x02, 0xFF)
    
    # Test a range of duty cycles
    await test_duty_cycle(dut, 0.0)
    await test_duty_cycle(dut, 0.25)
    await test_duty_cycle(dut, 0.50)
    await test_duty_cycle(dut, 0.75)
    await test_duty_cycle(dut, 1.0)

    dut._log.info("PWM Duty Cycle test completed successfully")
