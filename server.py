import argparse
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import ipaddress

# Store per-client state: expected sequence number, received packets, and forward socket
clients_state = {}
clients_lock = threading.Lock()

# Decode the data from the NBTP address format using the suffix of the IPv6 address
def decode_nbtp_address(ipv6_address, prefix_bits=64):
    # Convert textual IPv6 to integer
    addr = ipaddress.IPv6Address(ipv6_address)
    addr_int = int(addr)
    suffix_bits = 128 - prefix_bits
    # Mask off the low-order suffix bits
    suffix = addr_int & ((1 << suffix_bits) - 1)
    # First byte of suffix is the sequence number
    seq_num = (suffix >> (suffix_bits - 8)) & 0xFF
    # Remainder of suffix is payload
    data_int = suffix & ((1 << (suffix_bits - 8)) - 1)
    # Convert to bytes (handle zero-length)
    if data_int == 0:
        data_bytes = b""
    else:
        byte_len = (data_int.bit_length() + 7) // 8
        data_bytes = data_int.to_bytes(byte_len, byteorder="big")
    return seq_num, data_bytes

# Forward the decoded data to the target via a persistent TCP connection per client
def forward_to_destination(client_key, data, target_host, target_port, verbose):
    state = clients_state[client_key]
    # Create and cache a forward socket if needed
    if 'forward_sock' not in state:
        fsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        fsock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        fsock.connect((target_host, target_port))
        state['forward_sock'] = fsock
        if verbose:
            print(f"Opened TCP connection for {client_key} -> {target_host}:{target_port}")
    else:
        fsock = state['forward_sock']

    try:
        fsock.sendall(data)
        if verbose:
            print(f"Forwarded {len(data)} bytes for seq to {client_key}")
    except Exception as e:
        if verbose:
            print(f"Error forwarding to {target_host}:{target_port} for {client_key} - {e}")

# Send an ACK back to the client
def send_ack(sock, client_addr, seq_num, verbose):
    msg = f"ACK{seq_num}".encode()
    sock.sendto(msg, client_addr)
    if verbose:
        print(f"Sent ACK{seq_num} to {client_addr}")

# Send a NACK back to the client for missing packets
def send_nack(sock, client_addr, seq_num, verbose):
    msg = f"NACK{seq_num}".encode()
    sock.sendto(msg, client_addr)
    if verbose:
        print(f"Sent NACK{seq_num} to {client_addr}")

# Handle one incoming NBTP packet
def handle_nbtp_packet(packet, addr, sock, target_host, target_port, verbose, prefix_bits):
    client_key = (addr[0], addr[1])
    try:
        seq_num, payload = decode_nbtp_address(addr[0], prefix_bits)
        if verbose:
            print(f"Received from {client_key}: seq={seq_num}, {len(payload)} bytes")

        with clients_lock:
            state = clients_state.setdefault(client_key, {
                'expected_seq': 0,
                'received': {}
            })

        expected = state['expected_seq']
        # Duplicate packet
        if seq_num < expected:
            send_ack(sock, addr, seq_num, verbose)
            return
        # Out-of-order packet
        if seq_num > expected:
            state['received'][seq_num] = payload
            send_nack(sock, addr, expected, verbose)
            return
        # In-order packet
        forward_to_destination(client_key, payload, target_host, target_port, verbose)
        send_ack(sock, addr, seq_num, verbose)

        # Advance expected and drain buffered
        with clients_lock:
            state['expected_seq'] += 1
            while state['expected_seq'] in state['received']:
                next_seq = state['expected_seq']
                next_payload = state['received'].pop(next_seq)
                forward_to_destination(client_key, next_payload, target_host, target_port, verbose)
                send_ack(sock, addr, next_seq, verbose)
                state['expected_seq'] += 1

    except Exception as e:
        if verbose:
            print(f"Error in packet handler for {client_key}: {e}")

# Listen for NBTP packets on IPv6 via raw UDP and dispatch to handler threads
def listen_on_ipv6(bind_address, listen_port, target_host, target_port, max_workers, verbose, prefix_bits):
    thread_pool = ThreadPoolExecutor(max_workers=max_workers)
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_RAW, socket.IPPROTO_UDP)
        sock.bind((bind_address, listen_port))
        if verbose:
            print(f"Listening on [{bind_address}]:{listen_port} (IPv6 raw UDP)")
    except PermissionError:
        print("Permission denied: need root privileges to open raw socket.")
        sys.exit(1)
    except Exception as e:
        print(f"Error creating socket: {e}")
        sys.exit(1)

    while True:
        packet, addr = sock.recvfrom(4096)
        thread_pool.submit(
            handle_nbtp_packet,
            packet, addr, sock,
            target_host, target_port,
            verbose, prefix_bits
        )

# Entry point with argparse for robust CLI
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NBTP reordering gateway")
    parser.add_argument("--bind-address",    required=True,
                        help="IPv6 prefix to bind (e.g. 2001:db8:abcd:0012::)")
    parser.add_argument("--listen-port",     type=int, required=True,
                        help="UDP port on which NBTP clients send packets")
    parser.add_argument("--target-host",     required=True,
                        help="IPv4 or hostname of the SSH/target server")
    parser.add_argument("--target-port",     type=int, required=True,
                        help="TCP port of the SSH/target server")
    parser.add_argument("--max-workers",     type=int, default=4,
                        help="Max concurrent packet handlers")
    parser.add_argument("--verbose",         action="store_true",
                        help="Enable verbose logging")
    parser.add_argument("--prefix-bits",     type=int, default=64,
                        help="Number of high-order bits reserved for the IPv6 prefix")
    args = parser.parse_args()

    listen_on_ipv6(
        args.bind_address,
        args.listen_port,
        args.target_host,
        args.target_port,
        args.max_workers,
        args.verbose,
        args.prefix_bits
    )
