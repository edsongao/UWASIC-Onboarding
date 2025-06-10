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

async def measure_pwm_properties(dut, timeout_ns=1_000_000):
    """
    Measures period and high time of the PWM signal on uo_out[0] using manual polling.
    Returns (period_ns, high_time_ns).
    """
    start_time = cocotb.utils.get_sim_time(units="ns")

    # Synchronize to the start of a cycle (wait for a rising edge)
    # First, wait for the signal to be low
    while dut.uo_out[0].value == 1:
        await ClockCycles(dut.clk, 1)
        if cocotb.utils.get_sim_time(units="ns") - start_time > timeout_ns:
            dut._log.error("Timeout waiting for signal to go low.")
            return None, None
    
    # Then, wait for the signal to be high
    while dut.uo_out[0].value == 0:
        await ClockCycles(dut.clk, 1)
        if cocotb.utils.get_sim_time(units="ns") - start_time > timeout_ns:
            dut._log.error("Timeout waiting for signal to go high.")
            return None, None

    # We are now at a rising edge. Start measuring.
    t_rise1 = cocotb.utils.get_sim_time(units="ns")
    
    # Measure high time by waiting for the next falling edge
    while dut.uo_out[0].value == 1:
        await ClockCycles(dut.clk, 1)
    t_fall = cocotb.utils.get_sim_time(units="ns")
    high_time_ns = t_fall - t_rise1
    
    # Measure period by waiting for the next rising edge
    while dut.uo_out[0].value == 0:
        await ClockCycles(dut.clk, 1)
    t_rise2 = cocotb.utils.get_sim_time(units="ns")
    period_ns = t_rise2 - t_rise1

    return period_ns, high_time_ns

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

    # Configure PWM for a 50% duty cycle
    await send_spi_transaction(dut, 1, 0x00, 0x01) # Enable uo_out[0]
    await send_spi_transaction(dut, 1, 0x02, 0x01) # Enable PWM on uo_out[0]
    await send_spi_transaction(dut, 1, 0x04, 0x80) # Set duty cycle ~50%
    await ClockCycles(dut.clk, 500) # Wait for PWM to stabilize

    period_ns, _ = await measure_pwm_properties(dut)
    assert period_ns is not None, "Failed to measure PWM period."
    
    frequency_hz = 1 / (period_ns * 1e-9)
    dut._log.info(f"Measured Frequency: {frequency_hz:.2f} Hz")
    
    expected_freq_hz = 3000
    tolerance = 0.02 # 2% tolerance
    lower_bound = expected_freq_hz * (1 - tolerance)
    upper_bound = expected_freq_hz * (1 + tolerance)
    
    assert lower_bound <= frequency_hz <= upper_bound, \
        f"Frequency {frequency_hz:.2f} Hz is out of tolerance [{lower_bound:.2f}, {upper_bound:.2f}]"
    
    dut._log.info("PWM Frequency test completed successfully")

async def verify_duty_cycle(dut, duty_percent):
    """Helper to set and verify a specific duty cycle."""
    dut._log.info(f"----- Verifying Duty Cycle: {duty_percent}% -----")
    
    duty_value = int((duty_percent / 100.0) * 255)
    await send_spi_transaction(dut, 1, 0x04, duty_value)
    # Wait for a few periods for the change to take effect
    await ClockCycles(dut.clk, 35000)

    if duty_percent == 0:
        dut._log.info("Checking for static low signal.")
        assert dut.uo_out[0].value == 0, "Signal should be low for 0% duty cycle."
        # Monitor for a while to ensure no pulses appear
        await ClockCycles(dut.clk, 35000)
        assert dut.uo_out[0].value == 0, "Signal went high unexpectedly for 0% duty cycle."
        dut._log.info("✓ Correctly static low.")
        return

    if duty_percent == 100:
        dut._log.info("Checking for static high signal.")
        assert dut.uo_out[0].value == 1, "Signal should be high for 100% duty cycle."
        await ClockCycles(dut.clk, 35000)
        assert dut.uo_out[0].value == 1, "Signal went low unexpectedly for 100% duty cycle."
        dut._log.info("✓ Correctly static high.")
        return

    # Measure properties for non-edge cases
    period_ns, high_time_ns = await measure_pwm_properties(dut)
    assert period_ns is not None and high_time_ns is not None, f"Failed to measure PWM for {duty_percent}% duty cycle."

    measured_duty = (high_time_ns / period_ns) * 100.0
    dut._log.info(f"Expected: {duty_percent}%, Measured: {measured_duty:.2f}%")

    # Use a tolerance to account for digital quantization
    assert abs(measured_duty - duty_percent) < 2.0, \
        f"Measured duty {measured_duty:.2f}% is too far from expected {duty_percent}%"
    dut._log.info("✓ Duty cycle within tolerance.")

@cocotb.test()
async def test_pwm_duty(dut):
    dut._log.info("Start PWM Duty Cycle test")

    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    dut._log.info("Reset")
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    # Configure PWM for testing
    await send_spi_transaction(dut, 1, 0x00, 0x01) # Enable uo_out[0]
    await send_spi_transaction(dut, 1, 0x02, 0x01) # Enable PWM on uo_out[0]

    # Test a range of duty cycles, including edge cases
    await verify_duty_cycle(dut, 0)
    await verify_duty_cycle(dut, 25)
    await verify_duty_cycle(dut, 50)
    await verify_duty_cycle(dut, 75)
    await verify_duty_cycle(dut, 100)

    dut._log.info("PWM Duty Cycle test completed successfully")
