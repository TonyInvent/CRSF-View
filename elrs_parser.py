import serial
import struct
import time
import tkinter as tk
from tkinter import ttk
import threading
import queue
from threading import Thread
import os

# CRSF protocol constants
CRSF_ADDRESS_FLIGHT_CONTROLLER = 0xC8
CRSF_FRAMETYPE_RC_CHANNELS_PACKED = 0x16

def crc8_dvb_s2(crc, data):
    if isinstance(data, int):
        data = bytes([data])
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ 0xD5
            else:
                crc = crc << 1
        crc &= 0xFF
    return crc

def parse_channels(data):
    channels = []
    if len(data) != 22:  # CRSF packed channel data is 22 bytes
        return channels

    # Convert bytes to binary string
    bits = ''.join(format(byte, '08b')[::-1] for byte in data)

    # Extract 11-bit channel values
    for i in range(16):  # CRSF supports up to 16 channels
        start = i * 11
        end = start + 11
        if end <= len(bits):
            channel_bits = bits[start:end][::-1]
            channel_value = int(channel_bits, 2)
            channels.append(channel_value)

    return channels

class CRSFGui:
    def __init__(self, master):
        self.master = master
        master.title("CRSF Channel Data")

        self.channel_bars = []
        self.channel_labels = []

        for i in range(16):
            label = ttk.Label(master, text=f"CH{i+1:2d}:")
            label.grid(row=i, column=0, sticky="e", padx=5, pady=2)

            bar = ttk.Progressbar(master, length=200, maximum=1811-172)
            bar.grid(row=i, column=1, padx=5, pady=2)

            value_label = ttk.Label(master, text="0000")
            value_label.grid(row=i, column=2, sticky="w", padx=5, pady=2)

            self.channel_bars.append(bar)
            self.channel_labels.append(value_label)

        self.data_queue = queue.Queue()
        self.gui_queue = queue.Queue()
        self.channel_values = [0] * 16
        self.uart = None
        self.running = True
        self.init_serial()
        self.serial_thread = Thread(target=self.read_serial, daemon=True)
        self.processing_thread = Thread(target=self.process_data, daemon=True)
        self.serial_thread.start()
        self.processing_thread.start()

        # Lower priority for processing thread
        if hasattr(os, 'nice'):
            os.nice(10)  # Increase nice value (lower priority) on Unix-like systems

        self.master.after(10, self.update_gui)

    def init_serial(self):
        try:
            self.uart = serial.Serial('COM5', 420000, timeout=1)  # Adjust port and baudrate as needed
            print(f"Serial port opened: {self.uart.name}")
            self.uart.reset_input_buffer()
            print("Input buffer cleared")
        except serial.SerialException as e:
            print(f"Failed to open serial port: {e}")

    def update_gui(self):
        try:
            while True:
                channel, value = self.gui_queue.get_nowait()
                self.channel_bars[channel]['value'] = value - 172
                self.channel_labels[channel]['text'] = f"{value:4d}"
        except queue.Empty:
            pass
        finally:
            self.master.after(10, self.update_gui)

    def read_serial(self):
        if not self.uart:
            print("UART not initialized")
            return

        try:
            while self.running:
                data = self.uart.read(self.uart.in_waiting or 1)
                if data:
                    self.data_queue.put(data)
                time.sleep(0.001)  # Small sleep to prevent CPU hogging
        except serial.SerialException as e:
            print(f"Serial port error: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")
        finally:
            self.uart.close()
            print("Serial port closed")

    def process_data(self):
        buffer = bytearray()
        while self.running:
            try:
                data = self.data_queue.get(timeout=0.1)
                buffer.extend(data)

                while len(buffer) > 0:
                    if buffer[0] != CRSF_ADDRESS_FLIGHT_CONTROLLER:
                        buffer = buffer[1:]
                        continue

                    if len(buffer) < 2:
                        break

                    # Extract the complete frame from the buffer
                    frame_length = buffer[1]
                    if len(buffer) < frame_length + 2:
                        break

                    # Remove the processed frame from the buffer
                    frame = buffer[:frame_length + 2]
                    buffer = buffer[frame_length + 2:]

                    self.handle_frame(frame)

                time.sleep(0.001)  # Small sleep to prevent CPU hogging
            except queue.Empty:
                pass

    def handle_frame(self, frame):
        if len(frame) < 4:
            return

        # Extract the frame type (3rd byte of the frame)
        frame_type = frame[2]
        
        # Extract the payload (all bytes from the 4th byte to the second-to-last byte)
        payload = frame[3:-1]
        
        # Get the received CRC (last byte of the frame)
        received_crc = frame[-1]

        crc = crc8_dvb_s2(0, frame_type)
        crc = crc8_dvb_s2(crc, payload)

        if crc == received_crc and frame_type == CRSF_FRAMETYPE_RC_CHANNELS_PACKED:
            all_channels = parse_channels(payload)
            for i, value in enumerate(all_channels[:16]):
                if value != self.channel_values[i]:
                    self.channel_values[i] = value
                    self.gui_queue.put((i, value))

    def __del__(self):
        self.running = False
        if self.uart:
            self.uart.close()
            print("Serial port closed")

if __name__ == "__main__":
    root = tk.Tk()
    gui = CRSFGui(root)
    root.mainloop()