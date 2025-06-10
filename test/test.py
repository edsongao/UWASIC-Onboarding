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

# Returns the period between rising edges in nanoseconds, or 0 on timeout.
async def measure_freq(dut, timeout_ms=3):
    """
    Measures the period of dut.uo_out[0] using manual polling.
    This function first waits for a full rising edge to synchronize, then measures
    the time until the next rising edge.
    """
    timeout_ns = timeout_ms * 1_000_000
    start_measure_time = cocotb.utils.get_sim_time(units="ns")

    # --- Synchronization: Wait for the first rising edge to start cleanly ---
    # First, wait for the signal to be low (with timeout)
    while dut.uo_out[0].value == 1:
        await ClockCycles(dut.clk, 1)
        if (cocotb.utils.get_sim_time(units="ns") - start_measure_time) > timeout_ns:
            dut._log.error("Timeout waiting for signal to go low during sync.")
            return 0
    
    # Then, wait for the signal to go high (with timeout)
    while dut.uo_out[0].value == 0:
        await ClockCycles(dut.clk, 1)
        if (cocotb.utils.get_sim_time(units="ns") - start_measure_time) > timeout_ns:
            dut._log.error("Timeout waiting for signal to go high during sync.")
            return 0
    
    # --- Measurement: We are now at a rising edge ---
    t_rise1 = cocotb.utils.get_sim_time(units="ns")

    # Wait for the next falling edge
    while dut.uo_out[0].value == 1:
        await ClockCycles(dut.clk, 1)
        if (cocotb.utils.get_sim_time(units="ns") - t_rise1) > timeout_ns:
            dut._log.error("Timeout waiting for falling edge.")
            return 0

    # Wait for the second rising edge
    while dut.uo_out[0].value == 0:
        await ClockCycles(dut.clk, 1)
        if (cocotb.utils.get_sim_time(units="ns") - t_rise1) > timeout_ns:
            dut._log.error("Timeout waiting for second rising edge.")
            return 0
    
    t_rise2 = cocotb.utils.get_sim_time(units="ns")
    return t_rise2 - t_rise1

@cocotb.test()
async def test_pwm_freq(dut):
    dut._log.info("Start PWM frequency test")

    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut._log.info("Reset")
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    # --- FIX: Apply the comprehensive configuration from the working example ---
    # This ensures all necessary modules and pins are enabled.
    dut._log.info("Configuring PWM module with full enable sequence...")
    await send_spi_transaction(dut, 1, 0x00, 0xFF) # Enable uo_out
    await send_spi_transaction(dut, 1, 0x01, 0xFF) # Enable uio_out
    await send_spi_transaction(dut, 1, 0x02, 0xFF) # Select PWM for uo_out
    await send_spi_transaction(dut, 1, 0x03, 0xFF) # Select PWM for uio_out
    await send_spi_transaction(dut, 1, 0x04, 0x80) # Set duty cycle to ~50%
    
    # Measure the frequency
    period_ns = await measure_freq(dut)
    assert period_ns > 0, "Timeout while measuring frequency. PWM signal is not oscillating."
    
    frequency = 1 / (period_ns * 1e-9)
    dut._log.info(f"Measured frequency: {frequency:.2f} Hz")

    # Assert that the frequency is within 1% of the 3kHz target
    expected_freq = 3000
    tolerance = 0.01 
    assert expected_freq * (1 - tolerance) <= frequency <= expected_freq * (1 + tolerance), \
        f"Frequency {frequency:.2f} Hz is out of tolerance range [{expected_freq * (1 - tolerance):.2f}, {expected_freq * (1 + tolerance):.2f}]"

    dut._log.info("PWM Frequency test completed successfully")
