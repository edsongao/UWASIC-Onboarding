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

@cocotb.test() 
async def test_pwm_freq(dut):
    # Write your test here
    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    #initialize values for DUT

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

    #Sweep across lots of frequencies (THIS WAS LAST TESTED ON INCREMENT = 17, DROPPED TO SPEED UP)
    for freq in range(0, 256, 51): 
        dut._log.info(f"on duty cycle {(freq/255)*100}%")
        #Verify across every port
        for case in range(16):
            ui_in_val = await send_spi_transaction(dut, 1, 0x04, freq)
            #dut._log.info(f"enabling output. address {case//8+2} on pin {case % 8 + 1}")
            dut._log.info(f"Checking on pin {case + 1}")

            ui_in_val = await send_spi_transaction(dut, 1, case//8 + 2, 1 << (case % 8)) # enable output on pin 1
            ui_in_val = await send_spi_transaction(dut, 1, case//8, 1 << (case % 8)) # enable PWM on pin 1

            rising1, falling1, rising2 = await edgedetections(dut, case % 8 + 1, outstream = case//8)
            
            period = rising2 - rising1
            
            if freq == 0 or freq == 255: 
                #these wont work for frequency because its always on or off. below will throw error
                #You can check that if freq is 255. fallingedge should be -1 
                #and if freq is 0, rising edge 1 and 2 is -1
                dut._log.info(f"t_rising_edge1: {rising1}, t_rising_edge2: {rising2}, t_falling_edge: {falling1}")

            else:
                frequency = 1e9/period
                dut._log.info(f"t_rising_edge1: {rising1}, t_rising_edge2: {rising2}")
                dut._log.info(f"frequency is: {frequency}")
                assert frequency < 3030 and frequency > 2970


@cocotb.test()
async def test_pwm_duty(dut):

    #very similar deal. Since above test verified pins work and design spec states no behavioural
    #difference between pins, testing this on every pin is a waste. So pick one and sweep the frequencies

    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    #initialize values for DUT

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

    for case in range(0, 256, 17): 
        ui_in_val = await send_spi_transaction(dut, 1, 0x04, case)
        ui_in_val = await send_spi_transaction(dut, 1, 0x02, 0x01) # enable output on pin 1
        ui_in_val = await send_spi_transaction(dut, 1, 0x00, 0x01) # enable PWM on pin 1

        dut._log.info(f"Checking duty cycle at {round((case/255)*100, 2)}% (case: {case})")

        rising1, falling1, rising2 = await edgedetections(dut, 1, 0)
        
        if case == 0:
            #make sure it doesnt rise
            assert rising1 == -1
        elif case == 255:
            #make sure it doesn't fall
            assert falling1 == -1 
        else:
            period = rising2 - rising1
            hightime = falling1 - rising1

            dut._log.info(f"Expected Duty Cycle: {case/256}, actual duty cycle: {hightime/period}.")
            assert ((hightime/period)*100) == (case/256)*100, f"case failled. duty: {(case/255)*100}, actual duty: {(hightime/period)*100}"

            
    dut._log.info("PWM Duty Cycle test completed successfully")
