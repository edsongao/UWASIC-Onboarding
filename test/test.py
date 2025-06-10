# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, with_timeout, ClockCycles
from cocotb.types import Logic, LogicArray
import cocotb.utils
import cocotb.result

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
    
## PWM Frequency Test
@cocotb.test()
async def test_pwm_freq(dut):
    """
    Tests if the PWM frequency is within the specified tolerance.
    """
    dut._log.info("Start PWM frequency test")
    # Initialize the DUT and enable PWM
    await setup_dut(dut)

    # Set a 50% duty cycle (128/256) to ensure the signal toggles
    await send_spi_transaction(dut, 1, 0x04, 128)
    dut._log.info("Set duty cycle to 50% for frequency measurement.")

    # A 3kHz signal has a period of ~333us. We'll wait up to 1ms for an edge.
    timeout_us = 1000

    try:
        # Wait for the first rising edge
        await with_timeout(RisingEdge(dut.uo_out[0]), timeout_us, 'us')
        t_rise1 = cocotb.utils.get_sim_time(units='us')

        # Wait for the second rising edge to measure one full period
        await with_timeout(RisingEdge(dut.uo_out[0]), timeout_us, 'us')
        t_rise2 = cocotb.utils.get_sim_time(units='us')

        period_us = t_rise2 - t_rise1
        # Avoid division by zero
        if period_us == 0:
            assert False, "Measured period is zero."

        frequency_hz = 1 / (period_us * 1e-6)

        dut._log.info(f"Measured period: {period_us:.2f} us")
        dut._log.info(f"Calculated frequency: {frequency_hz:.2f} Hz")

        # Verify the frequency is within the 2970-3030 Hz range
        assert 2970 <= frequency_hz <= 3030, \
            f"Frequency {frequency_hz:.2f} Hz is out of tolerance (2970-3030 Hz)."

    except cocotb.result.SimTimeoutError:
        assert False, "Test timed out. PWM signal did not toggle as expected."

    dut._log.info("PWM Frequency test completed successfully")

## PWM Duty Cycle Test
@cocotb.test()
async def test_pwm_duty(dut):
    """
    Tests PWM duty cycle for 0%, 50%, and 100% cases.
    """
    dut._log.info("Start PWM duty cycle test")
    await setup_dut(dut)

    # A 3kHz signal has a period of ~333us. We'll use a 500us timeout.
    timeout_us = 500
    pwm_pin = dut.uo_out[0]

    # --- Test Case 1: 0% Duty Cycle (Always Low) ---
    dut._log.info("Testing 0% duty cycle (register value 0x00)")
    await send_spi_transaction(dut, 1, 0x04, 0x00)
    await ClockCycles(dut.clk, 10) # Wait for setting to apply
    
    try:
        # We expect a timeout here, as the signal should never rise
        await with_timeout(RisingEdge(pwm_pin), timeout_us, 'us')
        assert False, "PWM signal rose when it should be always low (0% duty)."
    except cocotb.result.SimTimeoutError:
        # This is the expected outcome.
        assert pwm_pin.value == 0, f"PWM pin should be low, but is {pwm_pin.value}"
        dut._log.info("Correctly timed out: signal remained low as expected.")

    # --- Test Case 2: 100% Duty Cycle (Always High) ---
    dut._log.info("Testing 100% duty cycle (register value 0xFF)")
    await send_spi_transaction(dut, 1, 0x04, 0xFF)
    await ClockCycles(dut.clk, 10) # Wait for setting to apply

    try:
        # We expect a timeout here, as the signal should never fall
        await with_timeout(FallingEdge(pwm_pin), timeout_us, 'us')
        assert False, "PWM signal fell when it should be always high (100% duty)."
    except cocotb.result.SimTimeoutError:
        # This is the expected outcome.
        assert pwm_pin.value == 1, f"PWM pin should be high, but is {pwm_pin.value}"
        dut._log.info("Correctly timed out: signal remained high as expected.")

    # --- Test Case 3: 50% Duty Cycle ---
    dut._log.info("Testing 50% duty cycle (register value 0x80)")
    await send_spi_transaction(dut, 1, 0x04, 128) # 128 is 50% of 256

    try:
        # Measure high time and period
        await with_timeout(RisingEdge(pwm_pin), timeout_us, 'us')
        t_rise = cocotb.utils.get_sim_time(units='us')

        await with_timeout(FallingEdge(pwm_pin), timeout_us, 'us')
        t_fall = cocotb.utils.get_sim_time(units='us')
        
        await with_timeout(RisingEdge(pwm_pin), timeout_us, 'us')
        t_rise2 = cocotb.utils.get_sim_time(units='us')

        high_time = t_fall - t_rise
        period = t_rise2 - t_rise
        measured_duty = (high_time / period) * 100

        dut._log.info(f"High time: {high_time:.2f} us, Period: {period:.2f} us")
        dut._log.info(f"Measured duty cycle: {measured_duty:.2f}%")

        # Check if the duty cycle is within a reasonable tolerance (e.g., +/- 2%)
        assert 48 <= measured_duty <= 52, \
            f"Measured duty cycle {measured_duty:.2f}% is not within 50% +/- 2% tolerance."

    except cocotb.result.SimTimeoutError:
        assert False, "Test timed out for 50% duty cycle. Signal not toggling."

    dut._log.info("PWM Duty Cycle test completed successfully")

