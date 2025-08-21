
import dronecan as uavcan

def decode_uavcan_v0_frame(can_id, data):
    """
    Decodes a UAVCAN v0 CAN frame and prints the decoded fields.

    Args:
        can_id (int): The 29-bit CAN ID.
        data (bytes): The CAN data payload.
    """

    # Decode the 29-bit CAN ID
    is_service = (can_id >> 25) & 0x01
    source_node_id = can_id & 0x7F

    print("--- CAN ID Fields ---")
    print(f"Priority: {(can_id >> 26) & 0x07}")

    if is_service:
        print("Frame Type: Service")
        print(f"Service Type ID: {(can_id >> 16) & 0xFF}")
        print(f"Request not Response: {(can_id >> 15) & 0x01}")
        print(f"Destination Node ID: {(can_id >> 8) & 0x7F}")
    else:
        print("Frame Type: Message")
        print(f"Message Type ID: {(can_id >> 8) & 0xFFFF}")

    print(f"Source Node ID: {source_node_id}")
    print("-" * 20)

    # Decode the Tail Byte from the data payload
    if data:
        tail_byte = data[-1]
        start_of_transfer = (tail_byte >> 7) & 0x01
        end_of_transfer = (tail_byte >> 6) & 0x01
        toggle_bit = (tail_byte >> 5) & 0x01
        transfer_id = tail_byte & 0x1F

        print("--- Tail Byte Fields ---")
        print(f"Start of Transfer: {start_of_transfer}")
        print(f"End of Transfer: {end_of_transfer}")
        print(f"Toggle Bit: {toggle_bit}")
        print(f"Transfer ID: {transfer_id}")
        print("-" * 20)

        # Display the payload data (excluding the tail byte)
        payload = data[:-1]
        print(f"Payload (hex): {payload.hex()}")
    else:
        print("No data payload.")

# --- Example Usage --
if __name__ == "__main__":
    print("### Decoding Here4 GPS frames ###")
    decode_uavcan_v0_frame(0x105E7100, b'\x01\x29\x00\x2c\x00\x16\x51\xd0')
    print("\n" * 2)
    decode_uavcan_v0_frame(0x1401557f, b'\xad\x00\x00\x00\x08\x00\x00\xcb')
