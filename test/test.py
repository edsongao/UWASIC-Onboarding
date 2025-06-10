# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import FallingEdge
from cocotb.triggers import ClockCycles
from cocotb.types import Logic
from cocotb.types import LogicArray
from cocotb.utils import get_sim_time

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
    ui_in_val = await send_spi_transaction(dut, 0, 0x00, 0xBE)
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

async def edgedetections(dut, outpos = 0, outstream=0):
    #if any of these are -1 on return, means nothing was actually set
    #Returns as a truple
    t_rising_edge1 = -1
    t_falling_edge1 = -1
    t_rising_edge2 = -1

    #other variables
    bit = (1 << outpos - 1)
    timeout_after_clk_cycles = 10000

    if outstream == 0:
        #wait for drop
        for _ in range(timeout_after_clk_cycles): 
            if int(dut.uo_out.value) &bit == 0:
                break
            await RisingEdge(dut.clk)

        #wait for first rising edge
        for _ in range(timeout_after_clk_cycles):
            if int(dut.uo_out.value) &bit != 0:
                t_rising_edge1 = get_sim_time(units="ns")
                break
            await RisingEdge(dut.clk)

        #wait for drop
        for _ in range(timeout_after_clk_cycles):
            if int(dut.uo_out.value) &bit == 0:
                t_falling_edge1 = get_sim_time(units="ns")
                break
            await RisingEdge(dut.clk)

        #wait for next rising edge
        for _ in range(timeout_after_clk_cycles):
            if int(dut.uo_out.value) &bit != 0:
                t_rising_edge2 = get_sim_time(units="ns")
                break
            await RisingEdge(dut.clk)
    else:
        for _ in range(timeout_after_clk_cycles): 
            if int(dut.uio_out.value) &bit == 0:
                break
            await RisingEdge(dut.clk)

        #wait for first rising edge
        for _ in range(timeout_after_clk_cycles):
            if int(dut.uio_out.value) &bit != 0:
                t_rising_edge1 = get_sim_time(units="ns")
                break
            await RisingEdge(dut.clk)

        #wait for drop
        for _ in range(timeout_after_clk_cycles):
            if int(dut.uio_out.value) &bit == 0:
                t_falling_edge1 = get_sim_time(units="ns")
                break
            await RisingEdge(dut.clk)

        #wait for next rising edge
        for _ in range(timeout_after_clk_cycles):
            if int(dut.uio_out.value) &bit != 0:
                t_rising_edge2 = get_sim_time(units="ns")
                break
            await RisingEdge(dut.clk)

    return t_rising_edge1, t_falling_edge1, t_rising_edge2
    
async def measure_pwm_edges(dut, pwm_pin, timeout_us=500):
    """
    Waits for and measures a full PWM cycle on a given pin.

    Args:
        dut: The device under test.
        pwm_pin: The specific pin object to monitor (e.g., dut.uo_out[0]).
        timeout_us: How long to wait for an edge before giving up.

    Returns:
        A tuple of (period_ns, high_time_ns).
        Returns (None, None) if a full cycle cannot be measured (e.g., timeout).
    """
    try:
        # Wait for a rising edge to start the measurement
        await with_timeout(RisingEdge(pwm_pin), timeout_us, 'us')
        t_rise1 = get_sim_time('ns')

        # Measure the high time
        await with_timeout(FallingEdge(pwm_pin), timeout_us, 'us')
        t_fall = get_sim_time('ns')

        # Measure the full period
        await with_timeout(RisingEdge(pwm_pin), timeout_us, 'us')
        t_rise2 = get_sim_time('ns')

        period_ns = t_rise2 - t_rise1
        high_time_ns = t_fall - t_rise1
        return (period_ns, high_time_ns)
    except cocotb.result.SimTimeoutError:
        # This is the expected result for 0% or 100% duty cycles
        return (None, None)

@cocotb.test()
async def test_pwm_freq(dut):
    """
    Verifies that the PWM frequency is stable and within spec.
    This test is optimized to check one pin thoroughly, as frequency should be
    independent of the duty cycle and pin number.
    """
    dut._log.info("Start PWM Frequency Test")
    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    # --- Reset Sequence ---
    dut.ena.value = 1
    dut.ui_in.value = ui_in_logicarray(ncs=1, bit=0, sclk=0)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    # --- Setup for Test ---
    # Enable PWM and output on a single, representative pin (e.g., pin 1, uo_out[0])
    # As per design spec, behavior should be identical across pins.
    await send_spi_transaction(dut, 1, 0x02, 0x01)  # Enable PWM on pin 1
    await send_spi_transaction(dut, 1, 0x00, 0x01)  # Enable output on pin 1

    # Set a 50% duty cycle for a stable, easily measurable signal
    await send_spi_transaction(dut, 1, 0x04, 128)
    dut._log.info("Testing frequency with a 50% duty cycle on pin uo_out[0].")

    # --- Measurement ---
    pwm_pin = dut.uo_out[0]
    period_ns, _ = await measure_pwm_edges(dut, pwm_pin)

    # --- Assertion ---
    assert period_ns is not None, "FAIL: Timed out waiting for PWM signal. Check enables."
    
    # Calculate frequency from the measured period in nanoseconds
    frequency_hz = 1e9 / period_ns
    dut._log.info(f"Measured Period: {period_ns} ns. Calculated Frequency: {frequency_hz:.2f} Hz")

    # Check if the frequency is within the required tolerance
    assert 2970 < frequency_hz < 3030, f"FAIL: Frequency {frequency_hz:.2f} Hz is out of spec [2970, 3030]."
    
    dut._log.info("PASS: PWM Frequency is within tolerance.")


@cocotb.test()
async def test_pwm_duty(dut):
    """
    Verifies PWM duty cycle accuracy by sweeping through a range of values.
    """
    dut._log.info("Start PWM Duty Cycle Test")
    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    # --- Reset Sequence ---
    dut.ena.value = 1
    dut.ui_in.value = ui_in_logicarray(ncs=1, bit=0, sclk=0)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    # --- Setup for Test ---
    # Enable a single pin for the sweep. We only need to do this once.
    await send_spi_transaction(dut, 1, 0x02, 0x01) # Enable PWM on pin 1
    await send_spi_transaction(dut, 1, 0x00, 0x01) # Enable output on pin 1
    pwm_pin = dut.uo_out[0]

    # --- Sweep and Test ---
    for duty_value in range(0, 256, 17):
        expected_duty_pct = (duty_value / 255.0) * 100
        dut._log.info(f"Testing duty cycle set to {duty_value}/255 (~{expected_duty_pct:.1f}%)")

        await send_spi_transaction(dut, 1, 0x04, duty_value)
        
        period_ns, high_time_ns = await measure_pwm_edges(dut, pwm_pin)

        if duty_value == 0:
            assert high_time_ns is None, "FAIL (0%): Signal should not rise, but it did."
            assert pwm_pin.value == 0, "FAIL (0%): Pin should be low, but it's high."
            dut._log.info("PASS: Signal correctly remained low.")
        elif duty_value == 255:
            assert high_time_ns is None, "FAIL (100%): Signal should not fall, but it did."
            assert pwm_pin.value == 1, "FAIL (100%): Pin should be high, but it's low."
            dut._log.info("PASS: Signal correctly remained high.")
        else:
            assert period_ns is not None, f"FAIL ({expected_duty_pct:.1f}%): Timed out waiting for signal."
            
            measured_duty_ratio = high_time_ns / period_ns
            expected_duty_ratio = duty_value / 256.0 # The PWM likely has 256 steps (0-255)

            dut._log.info(f"  Expected duty ratio: {expected_duty_ratio:.3f}. Measured: {measured_duty_ratio:.3f}")

            # Use a tolerance for floating point comparison! This is critical.
            # +/- 1% absolute tolerance.
            assert abs(measured_duty_ratio - expected_duty_ratio) < 0.01, \
                f"FAIL: Duty cycle mismatch. Expected ~{expected_duty_ratio:.3f}, got {measured_duty_ratio:.3f}"
            dut._log.info("PASS: Measured duty cycle is within tolerance.")
