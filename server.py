import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

# Store per-client state: expected sequence number and received packets
clients_state = {}
clients_lock = threading.Lock()

# Decode the data from the NBTP address format
def decode_nbtp_address(ipv6_address):
    _, *suffix_parts = ipv6_address.split(":")
    hex_data = ''.join(suffix_parts)
    seq_num = int(hex_data[:2], 16)
    data = bytes.fromhex(hex_data[2:])
    return seq_num, data

# Forward the decoded data to the target (e.g., SSH server), with retries
def forward_to_destination(data, target_host, target_port, verbose, max_retries=3):
    retries = 0
    while retries < max_retries:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as forward_sock:
                forward_sock.connect((target_host, target_port))
                forward_sock.sendall(data)
                if verbose:
                    print(f"Forwarded data to {target_host}:{target_port}")
            break  # Success, exit retry loop
        except Exception as e:
            retries += 1
            if retries < max_retries:
                if verbose:
                    print(f"Error forwarding to {target_host}:{target_port} - {e}. Retrying ({retries}/{max_retries})...")
                time.sleep(1)  # Brief delay before retrying
            else:
                if verbose:
                    print(f"Failed to forward to {target_host}:{target_port} after {max_retries} attempts - {e}")

# Send an acknowledgment (ACK) back to the client
def send_ack(sock, client_address, seq_num, verbose):
    ack_message = f"ACK{seq_num}".encode()
    sock.sendto(ack_message, client_address)
    if verbose:
        print(f"Sent ACK for seq_num {seq_num} to {client_address}")

# Send a negative acknowledgment (NACK) back to the client for missing packets
def send_nack(sock, client_address, seq_num, verbose):
    nack_message = f"NACK{seq_num}".encode()
    sock.sendto(nack_message, client_address)
    if verbose:
        print(f"Sent NACK for seq_num {seq_num} to {client_address}")

# Handle incoming NBTP packets from a specific client
def handle_nbtp_packet(client_ipv6, client_port, data, sock, target_host, target_port, verbose):
    global clients_state
    try:
        seq_num, decoded_data = decode_nbtp_address(client_ipv6)
        if verbose:
            print(f"Received packet with seq_num {seq_num} from {client_ipv6}")
        
        with clients_lock:
            if client_ipv6 not in clients_state:
                clients_state[client_ipv6] = {
                    "expected_sequence": 0,
                    "received_packets": {}
                }

            client_state = clients_state[client_ipv6]
            expected_sequence = client_state["expected_sequence"]
            received_packets = client_state["received_packets"]

            if seq_num > expected_sequence:
                received_packets[seq_num] = decoded_data
                send_nack(sock, (client_ipv6, client_port), expected_sequence, verbose)
                return

            if seq_num == expected_sequence:
                forward_to_destination(decoded_data, target_host, target_port, verbose)
                send_ack(sock, (client_ipv6, client_port), seq_num, verbose)
                client_state["expected_sequence"] += 1

                while client_state["expected_sequence"] in received_packets:
                    next_seq_num = client_state["expected_sequence"]
                    forward_to_destination(received_packets[next_seq_num], target_host, target_port, verbose)
                    send_ack(sock, (client_ipv6, client_port), next_seq_num, verbose)
                    del received_packets[next_seq_num]
                    client_state["expected_sequence"] += 1
        
    except Exception as e:
        if verbose:
            print(f"Error handling NBTP packet: {e}")

# Listen for NBTP packets on the IPv6 address
def listen_on_ipv6(bind_address, port, target_host, target_port, max_workers, verbose):
    thread_pool = ThreadPoolExecutor(max_workers=max_workers)  # Thread pool size configurable
    
    try:
        # Attempt to create a raw socket
        with socket.socket(socket.AF_INET6, socket.SOCK_RAW, socket.IPPROTO_RAW) as sock:
            sock.bind((bind_address, port))
            if verbose:
                print(f"Listening on {bind_address} for NBTP traffic...")

            while True:
                data, addr = sock.recvfrom(1024)
                client_ipv6 = addr[0]
                thread_pool.submit(handle_nbtp_packet, client_ipv6, addr[1], data, sock, target_host, target_port, verbose)

    except PermissionError:
        print("Permission denied: Raw socket requires superuser privileges. Please run as root or with elevated permissions.")
        sys.exit(1)
    except Exception as e:
        print(f"Error creating raw socket: {e}")
        sys.exit(1)

def main():
    if len(sys.argv) < 7:
        print("Usage: python3 server.py --bind-address <bind_address> --target-port <target_port> --target-host <target_host> --max-workers <max_workers> --verbose <true/false>")
        sys.exit(1)

    bind_address = sys.argv[2]
    target_port = int(sys.argv[4])
    target_host = sys.argv[6]
    max_workers = int(sys.argv[8])
    verbose = sys.argv[10].lower() == "true"

    # Listen for incoming NBTP traffic
    listen_on_ipv6(bind_address, target_port, target_host, target_port, max_workers, verbose)

if __name__ == "__main__":
    main()