# NoBody Transport Protocol (NBTP) — experimental Python prototype

NBTP sends **empty IPv6 UDP datagrams** whose **destination IPv6 addresses** carry small frames. It is an experiment, **not a secure VPN**, nor a standardized protocol. The current implementation supports **bidirectional TCP tunneling only** (for example a local SSH connection); it does not implement UDP application forwarding or production congestion control.

## Requirements and limitations

- Linux or another OS exposing Python `recvmsg`, `IPV6_RECVPKTINFO` and `IPV6_PKTINFO`.
- **Two different, routed IPv6 /64 prefixes**, one terminating at each endpoint. The destination address changes *for every packet*. A server bound only to one IPv6 address cannot receive these packets. Its kernel must consider the entire /64 local, e.g. using a Linux `local` route to `lo` (requires root to configure). A normal single IPv6 host address or an ISP that filters unassigned destinations is insufficient.
- An allowed UDP port (40444 by default) in both directions. Datagram bodies are empty, but **UDP headers are still present**; this is not invisible traffic.
- No native encryption, client authentication, replay protection, or rate limiting of network traffic. Never expose the target TCP port or this server on an untrusted network without additional protection. Binding the local TCP proxy to loopback by default helps.
- Only **3 bytes of application data per UDP datagram** with stop-and-wait retransmission; throughput will be extremely low, especially at non-local RTTs. No throughput, firewall-avoidance, or censorship-bypass claims have been verified.
- Both sides must use this version of the implementation; it is not wire-compatible with the old, broken code. At most 128 concurrent TCP streams are allowed per process; each 16-bit stream ID is random but not authenticated.

## Wire format

Each frame lives in the lower 64 bits of the destination IPv6 address of a configured `/64` network:

```
  stream ID    sequence      kind/length     bytes (zero-padded)
  16 bits      16 bits       8 bits         24 bits
  ----------------------------------------------------
  | stream  | sequence | type<<2 | length | data (0..3) |
  ----------------------------------------------------
```

The top three bits of kind/length are reserved and must be zero; the lower two bits indicate data length (0–3). Frame kinds are `DATA=0`, `OPEN=1`, `ACK=2`, `FIN=3`, and `RESET=4`. Control frames carry zero bytes. Any nonzero padding, unknown frame kind, invalid stream, or address outside the configured prefix is ignored. Sequence numbers wrap after 65535. Each direction uses one outstanding frame and retransmits until acknowledged (or a bounded retry limit expires). The receiver acknowledges a duplicate without forwarding it twice.

Only the destination address contains NBTP data. The server extracts it from `IPV6_PKTINFO` returned by `recvmsg`, **not from the sender's address**. All UDP bodies, including acknowledgments, have length zero. TCP responses travel back as empty UDP datagrams addressed into the client's prefix.

## Example Linux setup

Use two hosts with genuinely routed, non-overlapping IPv6 networks. These example `2001:db8::/32` networks are documentation-only and **will not route across the public Internet**. Have your network route `2001:db8:1::/64` to the client and `2001:db8:2::/64` to the server. Then on the respective machines:

Client (run the route command as a privileged administrator):

```bash
sudo ip -6 route add local 2001:db8:1::/64 dev lo
python3 client.py --local-prefix 2001:db8:1::/64 --remote-prefix 2001:db8:2::/64 --listen-port 2222 --udp-port 40444
```

Server (forward to an SSH daemon reachable only at `127.0.0.1:22`):

```bash
sudo ip -6 route add local 2001:db8:2::/64 dev lo
python3 server.py --local-prefix 2001:db8:2::/64 --remote-prefix 2001:db8:1::/64 --target-host 127.0.0.1 --target-port 22 --udp-port 40444
```

On the client, in another terminal:

```bash
ssh -p 2222 127.0.0.1
```

This is **not** an Internet-ready example: replace the documentation prefixes with two actually-routed /64 networks, restrict the peer on your firewall, and test in an isolated lab. Use `--verbose` for logging. The UDP port must be the same on both peers.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The tests run an in-process simulated IPv6 delivery path plus a real local TCP echo server. They cover frame encoding, binary zero-byte preservation, two-way TCP forwarding, FIN, retransmission after intentionally dropped DATA and ACK packets, and cleanup. They do **not** prove that real routers will deliver varying destination addresses. A real two-machine IPv6 test remains necessary before treating the tunnel as usable.

MIT-licensed, experimental research code.