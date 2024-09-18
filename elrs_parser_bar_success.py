import serial
import struct
import time
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

def channel_to_bar(value, max_length=50):
    normalized = (value - 172) / (1811 - 172)  # Normalize to 0-1 range
    bar_length = int(normalized * max_length)
    return '█' * bar_length + '░' * (max_length - bar_length)

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')

def main():
    ser = serial.Serial('COM5', 420000, timeout=1)  # Adjust port and baudrate as needed
    last_display_time = 0
    display_interval = 0.1  # Display update interval in seconds
    channel_values = [0] * 11  # Initialize with 11 channels

    try:
        while True:
            # Wait for the start of a frame
            while ser.read(1) != b'\xC8':
                pass

            # Read frame type and length
            frame_type_length = ser.read(2)
            if len(frame_type_length) != 2:
                continue

            frame_length, frame_type = frame_type_length
            
            # Read the payload
            payload = ser.read(frame_length - 2)  # -2 for type and length
            
            # Read the CRC
            received_crc = ser.read(1)[0]

            # Calculate CRC
            crc = crc8_dvb_s2(0, frame_type)
            crc = crc8_dvb_s2(crc, payload)

            if crc == received_crc and frame_type == CRSF_FRAMETYPE_RC_CHANNELS_PACKED:
                all_channels = parse_channels(payload)
                channel_values = all_channels[:16]  

            current_time = time.time()
            if current_time - last_display_time >= display_interval:
                clear_console()
                for i, value in enumerate(channel_values):
                    bar = channel_to_bar(value)
                    print(f"CH{i+1:2d}: {bar} {value:4d}")
                
                last_display_time = current_time

    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        ser.close()

if __name__ == "__main__":
    main()
