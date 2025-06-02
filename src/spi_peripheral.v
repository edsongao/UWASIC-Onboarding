/*
 * Copyright (c) 2024 Edson Gao
 * SPDX-License-Identifier: Apache-2.0
 */

module spi_peripheral (
    input wire clk,     // clock
    input wire rst_n,   // active-low reset
    
    input wire nCS,     // active-low chip select
    input wire SCLK,    // SPI clock
    input wire COPI,    // controller out peripheral in

    // output registers to pwm module
    output reg [7:0] en_reg_out_7_0,    //0x00
    output reg [7:0] en_reg_out_15_8,   //0x01
    output reg [7:0] en_reg_pwm_7_0,    //0x02
    output reg [7:0] en_reg_pwm_15_8,   //0x03
    output reg [7:0] pwm_duty_cycle     //0x04
);

    // Sync registers
    reg [1:0] SCLK_sync;
    reg [1:0] nCS_sync;
    reg [1:0] COPI_sync;
    
    reg [15:0] data_stream;     // Single capture register
    reg [4:0] SCLK_count;       // Counter for SCLK

    always @(posedge clk or negedge rst_n) begin
        // Reset state - everything goes to known values
        if (!rst_n) begin
            // Reset synchronizers
            SCLK_sync <= 2'b00;
            nCS_sync  <= 2'b11;  // nCS idles high
            COPI_sync <= 2'b00;
            
            // Reset SPI transaction state
            data_stream <= 16'h0000;
            SCLK_count <= 5'd0;
            
            // Reset output registers
            en_reg_out_7_0  <= 8'h00;
            en_reg_out_15_8 <= 8'h00;
            en_reg_pwm_7_0  <= 8'h00;
            en_reg_pwm_15_8 <= 8'h00;
            pwm_duty_cycle  <= 8'h00;
			
        end else begin
            // Always update synchronizers
            SCLK_sync <= {SCLK_sync[0], SCLK};
            nCS_sync  <= {nCS_sync[0], nCS};
            COPI_sync <= {COPI_sync[0], COPI};
            
            // nCS falling edge - transaction begin
            if (nCS_sync == 2'b10) begin
                data_stream <= 16'h0000;
                SCLK_count <= 5'd0;
            end
            
            // SCLK rising edge - capture data
            else if (SCLK_sync == 2'b01 && SCLK_count < 5'd16) begin
                data_stream <= {data_stream[14:0], COPI_sync[1]};
                SCLK_count <= SCLK_count + 1;
            end

            // nCS rising edge + complete transaction - process data
            else if (SCLK_count == 5'd16 && nCS_sync == 2'b01 && data_stream[15]) begin
                case (data_stream[14:8])  // Address field
                    7'h00: en_reg_out_7_0  <= data_stream[7:0];
                    7'h01: en_reg_out_15_8 <= data_stream[7:0];
                    7'h02: en_reg_pwm_7_0  <= data_stream[7:0];
                    7'h03: en_reg_pwm_15_8 <= data_stream[7:0];
                    7'h04: pwm_duty_cycle  <= data_stream[7:0];
                    default: ; // Ignore invalid addresses
                endcase
            end
        end
    end

endmodule
