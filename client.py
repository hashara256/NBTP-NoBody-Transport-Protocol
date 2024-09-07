import socket
import sys
import threading
import time

MAX_RETRIES = 5
ACK_TIMEOUT = 2
INITIAL_RETRANSMISSION_DELAY = 1  # Initial delay before retransmitting lost packets

# Dictionary to keep track of sent packets for potential retransmission
sent_packets = {}
# Lock for thread safety when accessing sent_packets
sent_packets_lock = threading.Lock()

# Encode the data into the NBTP address format
def encode_nbtp_address(remote_ipv6, seq_num, data):
    hex_data = data.hex()
    seq_hex = format(seq_num, '02x')  # Sequence number (1 byte)
    
    # Add sequence number at the start, and truncate or pad data to fit into the suffix
    suffix_data = seq_hex + hex_data[:32]  # Max 32 characters (16 bytes for data)
    
    # Ensure the suffix is padded if it's shorter than 32 characters
    suffix_data = suffix_data.ljust(32, '0')
    
    # Format the IPv6 address with the data encoded in the suffix
    full_ipv6_address = f"{remote_ipv6}:{':'.join(suffix_data[i:i+4] for i in range(0, len(suffix_data), 4))}"
    
    return full_ipv6_address

# Send the NBTP packet to the remote server
def send_packet_to_remote(sock, remote_ipv6, remote_port, seq_num, data, verbose, retransmission_delay):
    ipv6_address = encode_nbtp_address(remote_ipv6, seq_num, data)
    try:
        sock.sendto(b'', (ipv6_address, remote_port))
        if verbose:
            print(f"Sent packet with seq_num {seq_num} to {remote_ipv6}")
        
        with sent_packets_lock:
            sent_packets[seq_num] = (data, retransmission_delay)  # Save packet data for potential retransmission
    except Exception as e:
        if verbose:
            print(f"Error sending packet: {e}")

# Handle incoming ACKs or NACKs
def handle_ack(sock, verbose):
    while True:
        try:
            ack_data, addr = sock.recvfrom(1024)
            ack_message = ack_data.decode().strip()
            if ack_message.startswith("ACK"):
                ack_seq_num = int(ack_message[3:])
                if verbose:
                    print(f"Received ACK for seq_num {ack_seq_num}")
                with sent_packets_lock:
                    if ack_seq_num in sent_packets:
                        del sent_packets[ack_seq_num]  # Clean up sent packets once ACKed
            elif ack_message.startswith("NACK"):
                nack_seq_num = int(ack_message[4:])
                if verbose:
                    print(f"Received NACK for seq_num {nack_seq_num}, retransmitting...")
                with sent_packets_lock:
                    if nack_seq_num in sent_packets:
                        data, retransmission_delay = sent_packets[nack_seq_num]
                        new_delay = min(retransmission_delay * 2, 16)  # Exponential backoff with a max delay of 16s
                        send_packet_to_remote(sock, addr[0], addr[1], nack_seq_num, data, verbose, new_delay)
        except Exception as e:
            if verbose:
                print(f"Error receiving ACK/NACK: {e}")

# Handle incoming connections from local applications (e.g., SSH)
def handle_local_connection(local_conn, remote_ipv6, remote_port, sock, verbose):
    sequence_num = 0
    try:
        with local_conn:
            while True:
                data = local_conn.recv(1024)
                if not data:
                    break
                
                # Send the data without waiting for ACKs, but keep track for retransmission
                send_packet_to_remote(sock, remote_ipv6, remote_port, sequence_num, data, verbose, INITIAL_RETRANSMISSION_DELAY)
                sequence_num += 1
                time.sleep(0.1)  # Short delay to simulate continuous packet flow

    except Exception as e:
        if verbose:
            print(f"Error handling local connection: {e}")

# Listen for incoming connections on the local port (e.g., for SSH)
def listen_on_local_port(bind_address, listen_port, remote_ipv6, remote_port, verbose):
    sock = socket.socket(socket.AF_INET6, socket.SOCK_RAW, socket.IPPROTO_RAW)

    # Start the ACK handler thread
    ack_thread = threading.Thread(target=handle_ack, args=(sock, verbose))
    ack_thread.start()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as local_sock:
        local_sock.bind((bind_address, listen_port))
        local_sock.listen(5)
        if verbose:
            print(f"Listening on {bind_address}:{listen_port} for local connections...")

        while True:
            local_conn, addr = local_sock.accept()
            if verbose:
                print(f"Accepted local connection from {addr}")
            client_thread = threading.Thread(target=handle_local_connection, args=(local_conn, remote_ipv6, remote_port, sock, verbose))
            client_thread.start()

def main():
    if len(sys.argv) < 9:
        print("Usage: python3 client.py --bind-address <bind_address> --listen-port <listen_port> --remote-address <remote_ipv6> --remote-port <remote_port> --verbose <true/false>")
        sys.exit(1)

    bind_address = sys.argv[2]
    listen_port = int(sys.argv[4])
    remote_ipv6 = sys.argv[6]
    remote_port = int(sys.argv[8])
    verbose = sys.argv[10].lower() == "true"

    # Listen for incoming connections on the local port
    listen_on_local_port(bind_address, listen_port, remote_ipv6, remote_port, verbose)

if __name__ == "__main__":
    main()