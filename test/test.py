# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
# FIX 1: Import the missing 'FallingEdge' and 'Timer' triggers
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles, Timer
from cocotb.types import Logic
from cocotb.types import LogicArray

async def await_half_sclk(dut):
    """Wait for the SCLK signal to go high or low."""
    start_time = cocotb.utils.get_sim_time(units="ns")
    while True:
        await ClockCycles(dut.clk, 1)
        # Wait for half of the SCLK period (10 us)
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
    
    Parameters:
    - r_w: boolean, True for write, False for read
    - address: int, 7-bit address (0-127)
    - data: LogicArray or int, 8-bit data
    """
    # Convert data to int if it's a LogicArray
    if isinstance(data, LogicArray):
        data_int = int(data)
    else:
        data_int = data
    # Validate inputs
    if address < 0 or address > 127:
        raise ValueError("Address must be 7-bit (0-127)")
    if data_int < 0 or data_int > 255:
        raise ValueError("Data must be 8-bit (0-255)")
    # Combine RW and address into first byte
    first_byte = (int(r_w) << 7) | address
    # Start transaction - pull CS low
    sclk = 0
    ncs = 0
    bit = 0
    # Set initial state with CS low
    dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
    await ClockCycles(dut.clk, 1)
    # Send first byte (RW + Address)
    for i in range(8):
        bit = (first_byte >> (7-i)) & 0x1
        # SCLK low, set COPI
        sclk = 0
        dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
        await await_half_sclk(dut)
        # SCLK high, keep COPI
        sclk = 1
        dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
        await await_half_sclk(dut)
    # Send second byte (Data)
    for i in range(8):
        bit = (data_int >> (7-i)) & 0x1
        # SCLK low, set COPI
        sclk = 0
        dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
        await await_half_sclk(dut)
        # SCLK high, keep COPI
        sclk = 1
        dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
        await await_half_sclk(dut)
    # End transaction - return CS high
    sclk = 0
    ncs = 1
    bit = 0
    dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
    await ClockCycles(dut.clk, 600)
    return ui_in_logicarray(ncs, bit, sclk)

@cocotb.test()
async def test_spi(dut):
    dut._log.info("Start SPI test")

    # Set the clock period to 100 ns (10 MHz)
    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut._log.info("Reset")
    dut.ena.value = 1
    ncs = 1
    bit = 0
    sclk = 0
    dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    dut._log.info("Test project behavior")
    dut._log.info("Write transaction, address 0x00, data 0xF0")
    ui_in_val = await send_spi_transaction(dut, 1, 0x00, 0xF0)  # Write transaction
    assert dut.uo_out.value == 0xF0, f"Expected 0xF0, got {dut.uo_out.value}"
    await ClockCycles(dut.clk, 1000) 

    dut._log.info("Write transaction, address 0x01, data 0xCC")
    ui_in_val = await send_spi_transaction(dut, 1, 0x01, 0xCC)  # Write transaction
    assert dut.uio_out.value == 0xCC, f"Expected 0xCC, got {dut.uio_out.value}"
    await ClockCycles(dut.clk, 100)

    dut._log.info("Write transaction, address 0x30 (invalid), data 0xAA")
    ui_in_val = await send_spi_transaction(dut, 1, 0x30, 0xAA)
    await ClockCycles(dut.clk, 100)

    dut._log.info("Read transaction (invalid), address 0x00, data 0xBE")
    ui_in_val = await send_spi_transaction(dut, 0, 0x30, 0xBE)
    assert dut.uo_out.value == 0xF0, f"Expected 0xF0, got {dut.uo_out.value}"
    await ClockCycles(dut.clk, 100)
    
    dut._log.info("Read transaction (invalid), address 0x41 (invalid), data 0xEF")
    ui_in_val = await send_spi_transaction(dut, 0, 0x41, 0xEF)
    await ClockCycles(dut.clk, 100)

    dut._log.info("Write transaction, address 0x02, data 0xFF")
    ui_in_val = await send_spi_transaction(dut, 1, 0x02, 0xFF)  # Write transaction
    await ClockCycles(dut.clk, 100)

    dut._log.info("Write transaction, address 0x04, data 0xCF")
    ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0xCF)  # Write transaction
    await ClockCycles(dut.clk, 30000)

    dut._log.info("Write transaction, address 0x04, data 0xFF")
    ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0xFF)  # Write transaction
    await ClockCycles(dut.clk, 30000)

    dut._log.info("Write transaction, address 0x04, data 0x00")
    ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0x00)  # Write transaction
    await ClockCycles(dut.clk, 30000)

    dut._log.info("Write transaction, address 0x04, data 0x01")
    ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0x01)  # Write transaction
    await ClockCycles(dut.clk, 30000)

    dut._log.info("SPI test completed successfully")

@cocotb.test()
async def test_pwm_freq(dut):
    dut._log.info("Start PWM frequency test")

    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    dut._log.info("Reset")
    dut.ena.value = 1
    ncs = 1
    bit = 0
    sclk = 0
    dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)
    
    dut._log.info("Configuring PWM for frequency measurement")
    await send_spi_transaction(dut, 1, 0x01, 0x01)  # Enable uio_out[0]
    await send_spi_transaction(dut, 1, 0x02, 0x01)  # Enable PWM on uio_out[0]
    await send_spi_transaction(dut, 1, 0x04, 0x80)  # Set duty cycle to 50%

    await ClockCycles(dut.clk, 1000)
    
    dut._log.info("Waiting for the first rising edge to measure period...")
    # FIX 2: Monitor uio_out[0] instead of uo_out[0]
    await RisingEdge(dut.uio_out[0])
    t_rise1 = cocotb.utils.get_sim_time(units='ns')
    dut._log.info(f"First rising edge detected at {t_rise1:.2f} ns")

    dut._log.info("Waiting for the second rising edge...")
    # FIX 2: Monitor uio_out[0] instead of uo_out[0]
    await RisingEdge(dut.uio_out[0])
    t_rise2 = cocotb.utils.get_sim_time(units='ns')
    dut._log.info(f"Second rising edge detected at {t_rise2:.2f} ns")
    
    period_ns = t_rise2 - t_rise1
    assert period_ns > 0, "Measured period is not positive, cannot calculate frequency."
    
    frequency_hz = 1 / (period_ns * 1e-9)
    dut._log.info(f"Measured Period: {period_ns:.2f} ns, Calculated Frequency: {frequency_hz:.2f} Hz")
    
    expected_freq_hz = 3000
    tolerance = 0.02
    lower_bound = expected_freq_hz * (1 - tolerance)
    upper_bound = expected_freq_hz * (1 + tolerance)
    
    assert lower_bound <= frequency_hz <= upper_bound, \
        f"Frequency {frequency_hz:.2f} Hz is out of tolerance range [{lower_bound:.2f}, {upper_bound:.2f}] Hz"
    
    dut._log.info("PWM Frequency test completed successfully")


async def set_and_verify_duty_cycle(dut, duty_cycle_percent):
    """Helper coroutine to set a duty cycle and verify the output waveform."""
    dut._log.info(f"----- Testing Duty Cycle: {duty_cycle_percent}% -----")
    
    if not (0 <= duty_cycle_percent <= 100):
        raise ValueError("Duty cycle must be between 0 and 100.")
    duty_value = int((duty_cycle_percent / 100.0) * 255)
    await send_spi_transaction(dut, 1, 0x04, duty_value)
    
    await Timer(400, 'us')

    # FIX 2: Monitor uio_out[0] for all PWM-related checks
    if duty_cycle_percent == 0:
        dut._log.info("Verifying 0% duty cycle: signal should be constantly low.")
        assert dut.uio_out[0].value == 0, f"Signal was high for 0% duty cycle"
        dut._log.info("Correctly low for 0% duty cycle.")
        return
        
    if duty_cycle_percent == 100:
        dut._log.info("Verifying 100% duty cycle: signal should be constantly high.")
        assert dut.uio_out[0].value == 1, f"Signal was low for 100% duty cycle"
        dut._log.info("Correctly high for 100% duty cycle.")
        return

    await RisingEdge(dut.uio_out[0])
    t_rise1 = cocotb.utils.get_sim_time(units='ns')

    await FallingEdge(dut.uio_out[0])
    t_fall = cocotb.utils.get_sim_time(units='ns')

    await RisingEdge(dut.uio_out[0])
    t_rise2 = cocotb.utils.get_sim_time(units='ns')
    
    high_time_ns = t_fall - t_rise1
    period_ns = t_rise2 - t_rise1
    
    assert period_ns > 0, "Measured period is not positive."

    measured_duty_cycle = (high_time_ns / period_ns) * 100.0
    dut._log.info(f"Expected DC: {duty_cycle_percent}%, Measured DC: {measured_duty_cycle:.2f}%")
    
    assert abs(measured_duty_cycle - duty_cycle_percent) < 2.0, \
        f"Measured DC {measured_duty_cycle:.2f}% deviates too much from expected {duty_cycle_percent}%"
    dut._log.info(f"Duty cycle measurement within tolerance.")

@cocotb.test()
async def test_pwm_duty(dut):
    dut._log.info("Start PWM Duty Cycle test suite")

    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    dut._log.info("Reset")
    dut.ena.value = 1
    ncs = 1
    bit = 0
    sclk = 0
    dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    dut._log.info("Configuring PWM for duty cycle tests")
    await send_spi_transaction(dut, 1, 0x01, 0x01)  # Enable uio_out[0]
    await send_spi_transaction(dut, 1, 0x02, 0x01)  # Enable PWM on uio_out[0]

    duty_cycles_to_test = [0, 1, 25, 50, 75, 99, 100]
    for dc in duty_cycles_to_test:
        await set_and_verify_duty_cycle(dut, dc)

    dut._log.info("PWM Duty Cycle test completed successfully")
