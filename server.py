"""NBTP IPv6 destination-address receiver and TCP forwarding server."""
import argparse
import logging
from nbtp import Endpoint


def main():
    parser = argparse.ArgumentParser(description="Experimental NBTP TCP server")
    parser.add_argument("--local-prefix", required=True, help="Locally-routed server IPv6 /64")
    parser.add_argument("--remote-prefix", required=True, help="Routed client IPv6 /64")
    parser.add_argument("--udp-port", type=int, default=40444)
    parser.add_argument("--target-host", required=True)
    parser.add_argument("--target-port", type=int, required=True)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    Endpoint(args.local_prefix, args.remote_prefix, args.udp_port,
             target=(args.target_host, args.target_port)).listen()


if __name__ == "__main__":
    main()
