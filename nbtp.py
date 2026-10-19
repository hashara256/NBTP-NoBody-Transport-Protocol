"""NBTP experimental bidirectional TCP tunnel carried in IPv6 destination addresses.

All NBTP datagrams have zero-length UDP payloads. The 64-bit host part of the
IPv6 *destination* carries a frame. Each side needs an IPv6 /64 routed locally;
see README for the Linux routing requirements. No authentication or encryption.
"""
from __future__ import annotations

import ipaddress
import logging
import secrets
import socket
import struct
import threading
from dataclasses import dataclass

LOG = logging.getLogger("nbtp")
MAX_DATA = 3
TIMEOUT = 0.5
MAX_RETRIES = 12
MAX_SESSIONS = 128
OPEN = 1
ACK = 2
FIN = 3
RESET = 4
DATA = 0
KINDS = {DATA, OPEN, ACK, FIN, RESET}


@dataclass(frozen=True)
class Frame:
    kind: int
    stream: int
    sequence: int
    data: bytes = b""

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError("unknown frame kind")
        if not 1 <= self.stream <= 65535:
            raise ValueError("stream must be 1..65535")
        if not 0 <= self.sequence <= 65535:
            raise ValueError("sequence must be 0..65535")
        if len(self.data) > MAX_DATA or (self.kind != DATA and self.data):
            raise ValueError("invalid frame payload")
        if self.kind == DATA and not self.data:
            raise ValueError("data frame cannot be empty")


def ipv6_prefix(value):
    network = ipaddress.IPv6Network(value, strict=True)
    if network.prefixlen != 64:
        raise ValueError("NBTP requires a routed IPv6 /64 prefix")
    return network


def encode_address(network, frame):
    """Encode a frame in the lower 64 bits of an IPv6 *destination*."""
    network = ipv6_prefix(str(network))
    tag = (frame.kind << 2) | len(frame.data)
    suffix = struct.pack("!HHB3s", frame.stream, frame.sequence, tag,
                         frame.data.ljust(MAX_DATA, b"\0"))
    return str(ipaddress.IPv6Address(int(network.network_address) | int.from_bytes(suffix, "big")))


def decode_address(network, address):
    network = ipv6_prefix(str(network))
    dest = ipaddress.IPv6Address(address)
    if dest not in network:
        raise ValueError("destination outside configured prefix")
    stream, sequence, tag, padded = struct.unpack("!HHB3s", (int(dest) & ((1 << 64) - 1)).to_bytes(8, "big"))
    if tag & 0xE0:
        raise ValueError("invalid reserved flag bits")
    kind, size = tag >> 2, tag & 3
    if padded[size:] != b"\0" * (MAX_DATA - size):
        raise ValueError("invalid padding")
    return Frame(kind, stream, sequence, padded[:size])


class Session:
    """One duplex TCP connection; stop-and-wait ACKs in each direction.

    Stop-and-wait deliberately trades throughput for correctness and avoids
    ambiguity when 16-bit sequence numbers wrap.
    """
    def __init__(self, endpoint, stream, tcp_sock, *, server_side=False):
        self.endpoint = endpoint
        self.stream = stream
        self.sock = tcp_sock
        self.server_side = server_side
        self.tx_sequence = 1 if server_side else 0
        self.rx_sequence = 1
        self.tx_lock = threading.Lock()
        self.rx_lock = threading.Lock()
        self.ack_event = threading.Event()
        self.pending = None
        self.tx_finished = False
        self.rx_finished = False
        self.closed = False
        self.close_lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._read_tcp, daemon=True,
                         name=f"nbtp-tcp-{self.stream}").start()

    def _reliable_send(self, kind, data=b""):
        with self.tx_lock:
            seq = self.tx_sequence
            frame = Frame(kind, self.stream, seq, data)
            self.pending = seq
            self.ack_event.clear()
            for attempt in range(MAX_RETRIES):
                if self.closed:
                    break
                self.endpoint.send(frame)
                if self.ack_event.wait(TIMEOUT) and not self.closed:
                    self.pending = None
                    self.tx_sequence = (seq + 1) & 0xffff
                    return True
                LOG.debug("retrying stream=%d seq=%d attempt=%d", self.stream, seq, attempt + 1)
            self.pending = None
            self.abort(send_reset=True)
            return False

    def _read_tcp(self):
        try:
            if not self.server_side and not self._reliable_send(OPEN):
                return
            while not self.closed:
                data = self.sock.recv(4096)
                if not data:
                    break
                for start in range(0, len(data), MAX_DATA):
                    if not self._reliable_send(DATA, data[start:start + MAX_DATA]):
                        return
            if not self.closed and self._reliable_send(FIN):
                self.tx_finished = True
                self._maybe_close()
        except OSError as exc:
            LOG.warning("TCP stream %d ended: %s", self.stream, exc)
            self.abort(send_reset=True)

    def ack(self, seq):
        if self.pending == seq:
            self.ack_event.set()

    def receive(self, frame):
        if frame.kind == ACK:
            self.ack(frame.sequence)
            return
        if frame.kind == RESET:
            self.abort()
            return
        if frame.kind == OPEN:
            if self.server_side and frame.sequence == 0:
                self.endpoint.send(Frame(ACK, self.stream, 0))
            return
        with self.rx_lock:
            if frame.sequence == ((self.rx_sequence - 1) & 0xffff):
                # A duplicate: resend ACK, do not forward data twice.
                self.endpoint.send(Frame(ACK, self.stream, frame.sequence))
                return
            if frame.sequence != self.rx_sequence or self.rx_finished:
                return
            try:
                if frame.kind == DATA:
                    self.sock.sendall(frame.data)
                elif frame.kind == FIN:
                    self.rx_finished = True
                    self.sock.shutdown(socket.SHUT_WR)
                else:
                    return
            except OSError:
                self.abort(send_reset=True)
                return
            self.rx_sequence = (self.rx_sequence + 1) & 0xffff
            self.endpoint.send(Frame(ACK, self.stream, frame.sequence))
            self._maybe_close()

    def _maybe_close(self):
        if self.tx_finished and self.rx_finished:
            self.abort()

    def abort(self, *, send_reset=False):
        with self.close_lock:
            if self.closed:
                return
            self.closed = True
        if send_reset:
            try:
                self.endpoint.send(Frame(RESET, self.stream, 0))
            except OSError:
                pass
        self.ack_event.set()
        try:
            self.sock.close()
        except OSError:
            pass
        self.endpoint.remove(self.stream, self)


class Endpoint:
    """IPv6 UDP listener with IPV6_RECVPKTINFO for the local destination address.

    `send_frame` may be injected to run deterministic offline transport tests.
    """
    def __init__(self, local_prefix, remote_prefix, udp_port, *, target=None, send_frame=None):
        self.local_prefix = ipv6_prefix(local_prefix)
        self.remote_prefix = ipv6_prefix(remote_prefix)
        if self.local_prefix == self.remote_prefix:
            raise ValueError("local and remote /64 prefixes must differ")
        self.udp_port = udp_port
        self.target = target
        self.send_frame = send_frame
        self.sessions = {}
        self.sessions_lock = threading.Lock()
        self.socket = None

    def send(self, frame):
        addr = encode_address(self.remote_prefix, frame)
        if self.send_frame is not None:
            self.send_frame(addr)
        else:
            self.socket.sendto(b"", (addr, self.udp_port))

    def remove(self, stream, session):
        with self.sessions_lock:
            if self.sessions.get(stream) is session:
                del self.sessions[stream]

    def add_local_tcp(self, tcp_sock):
        with self.sessions_lock:
            if len(self.sessions) >= MAX_SESSIONS:
                raise RuntimeError("no available stream IDs")
            for _ in range(65536):
                stream = secrets.randbelow(65535) + 1
                if stream not in self.sessions:
                    break
            else:
                tcp_sock.close()
                raise RuntimeError("cannot allocate stream")
            session = Session(self, stream, tcp_sock)
            self.sessions[stream] = session
        session.start()
        return session

    def deliver(self, destination, payload=b""):
        if payload:
            return  # NBTP intentionally has no UDP body
        try:
            frame = decode_address(self.local_prefix, destination)
        except ValueError:
            return
        with self.sessions_lock:
            session = self.sessions.get(frame.stream)
            if session is None and frame.kind == OPEN and frame.sequence == 0 and self.target:
                if len(self.sessions) >= MAX_SESSIONS:
                    self.send(Frame(RESET, frame.stream, 0))
                    return
                try:
                    tcp_sock = socket.create_connection(self.target, timeout=3)
                    tcp_sock.settimeout(None)
                except OSError as exc:
                    LOG.warning("failed to connect target: %s", exc)
                    self.send(Frame(RESET, frame.stream, 0))
                    return
                session = Session(self, frame.stream, tcp_sock, server_side=True)
                self.sessions[frame.stream] = session
                session.start()
        if session is not None:
            session.receive(frame)
        elif frame.kind != RESET:
            self.send(Frame(RESET, frame.stream, 0))

    def open_socket(self):
        if self.socket is not None:
            return self.socket
        if not hasattr(socket, "IPV6_RECVPKTINFO") or not hasattr(socket.socket, "recvmsg"):
            raise RuntimeError("requires an OS supporting IPV6_RECVPKTINFO and recvmsg")
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_RECVPKTINFO, 1)
            sock.bind(("::", self.udp_port))
        except BaseException:
            sock.close()
            raise
        self.socket = sock
        LOG.info("NBTP listening on [::]:%d for %s", self.udp_port, self.local_prefix)
        return sock

    def listen(self):
        sock = self.open_socket()
        while True:
            payload, control, flags, source = sock.recvmsg(1024, socket.CMSG_SPACE(20))
            if flags & getattr(socket, "MSG_CTRUNC", 8):
                continue
            for level, typ, value in control:
                if (level == socket.IPPROTO_IPV6 and typ == socket.IPV6_PKTINFO
                        and len(value) >= 20):
                    dest = socket.inet_ntop(socket.AF_INET6, value[:16])
                    self.deliver(dest, payload)
                    break
