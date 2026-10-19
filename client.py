"""NBTP local TCP-to-IPv6 tunnel client."""
import argparse
import logging
import socket
import threading
from nbtp import Endpoint


def main():
    parser = argparse.ArgumentParser(description="Experimental NBTP TCP client")
    parser.add_argument("--local-prefix", required=True, help="Locally-routed client IPv6 /64")
    parser.add_argument("--remote-prefix", required=True, help="Routed server IPv6 /64")
    parser.add_argument("--udp-port", type=int, default=40444)
    parser.add_argument("--bind-address", default="127.0.0.1", help="Local TCP listen address")
    parser.add_argument("--listen-port", type=int, required=True, help="Local TCP listen port")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    endpoint = Endpoint(args.local_prefix, args.remote_prefix, args.udp_port)
    endpoint.open_socket()  # fail visibly if UDP cannot be bound
    threading.Thread(target=endpoint.listen, daemon=True).start()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((args.bind_address, args.listen_port))
        listener.listen()
        logging.info("Forwarding TCP %s:%s over NBTP", args.bind_address, args.listen_port)
        while True:
            conn, _ = listener.accept()
            endpoint.add_local_tcp(conn)


if __name__ == "__main__":
    main()
