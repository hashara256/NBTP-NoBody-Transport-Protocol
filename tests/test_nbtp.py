import ipaddress
import queue
import socket
import socketserver
import threading
import time
import unittest
from unittest.mock import patch

import nbtp
from nbtp import ACK, DATA, FIN, OPEN, RESET, Endpoint, Frame, decode_address, encode_address

A = "2001:db8:1::/64"
B = "2001:db8:2::/64"


class CodecTests(unittest.TestCase):
    def test_round_trip_all_bytes_and_lengths(self):
        for length in (1, 2, 3):
            for value in (0, 1, 127, 255):
                payload = bytes([value]) * length
                frame = Frame(DATA, 65535, 65535, payload)
                encoded = encode_address(B, frame)
                self.assertIn(ipaddress.IPv6Address(encoded), ipaddress.IPv6Network(B))
                self.assertEqual(frame, decode_address(B, encoded))

    def test_control_frames_and_flag_validation(self):
        for kind in (OPEN, ACK, FIN, RESET):
            frame = Frame(kind, 2, 65535)
            self.assertEqual(decode_address(B, encode_address(B, frame)), frame)
        with self.assertRaises(ValueError):
            Frame(DATA, 4, 0, b"1234")
        with self.assertRaises(ValueError):
            Frame(DATA, 4, 0, b"")
        with self.assertRaises(ValueError):
            Frame(ACK, 4, 0, b"a")
        with self.assertRaises(ValueError):
            decode_address(A, encode_address(B, Frame(DATA, 1, 1, b"X")))
        with self.assertRaises(ValueError):
            decode_address(B, str(ipaddress.IPv6Address(int(ipaddress.IPv6Network(B).network_address) | (1 << 24) | (0x80 << 24))))
        with self.assertRaises(ValueError):
            nbtp.ipv6_prefix("2001:db8::/48")


class EchoHandler(socketserver.BaseRequestHandler):
    def handle(self):
        while data := self.request.recv(4096):
            self.request.sendall(data)


class TunnelTests(unittest.TestCase):
    def setUp(self):
        self.echo = socketserver.ThreadingTCPServer(("127.0.0.1", 0), EchoHandler)
        self.echo.daemon_threads = True
        self.echo_thread = threading.Thread(target=self.echo.serve_forever, daemon=True)
        self.echo_thread.start()
        self.wire = queue.Queue()
        self.drop_once = set()
        self.dropped = set()
        self.cl = Endpoint(A, B, 40444, send_frame=lambda dest: self.wire.put(("server", dest)))
        self.sv = Endpoint(B, A, 40444, target=self.echo.server_address,
                           send_frame=lambda dest: self.wire.put(("client", dest)))
        self.stopping = threading.Event()
        self.worker = threading.Thread(target=self._relay, daemon=True)
        self.worker.start()
        self.socket_app, self.socket_nbtp = socket.socketpair()
        self.socket_app.settimeout(10)

    def _relay(self):
        while not self.stopping.is_set():
            try:
                role, address = self.wire.get(timeout=0.05)
            except queue.Empty:
                continue
            receiver = self.sv if role == "server" else self.cl
            frame = decode_address(receiver.local_prefix, address)
            key = (role, frame.kind)
            if key in self.drop_once and key not in self.dropped:
                self.dropped.add(key)
                continue
            receiver.deliver(address)

    def tearDown(self):
        self.stopping.set()
        self.socket_app.close()
        for side in (self.cl, self.sv):
            for s in list(side.sessions.values()):
                s.abort()
        self.echo.shutdown()
        self.echo.server_close()
        self.worker.join(2)

    def exchange(self, message):
        self.cl.add_local_tcp(self.socket_nbtp)
        self.socket_app.sendall(message)
        self.socket_app.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            part = self.socket_app.recv(4096)
            if not part:
                break
            chunks.append(part)
        self.assertEqual(b"".join(chunks), message)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if not self.cl.sessions and not self.sv.sessions:
                break
            time.sleep(0.01)
        self.assertEqual(self.cl.sessions, {})
        self.assertEqual(self.sv.sessions, {})

    def test_bidirectional_binary_tcp(self):
        self.exchange(b"\x00\x01HELLO\x00\xff\x00This is a multi-packet message")

    def test_retransmit_lost_data_and_ack(self):
        self.drop_once = {("server", DATA), ("client", ACK)}
        with patch.object(nbtp, "TIMEOUT", 0.08):
            self.exchange(b"retry\x00payload")
        self.assertEqual(self.drop_once, self.dropped)


if __name__ == "__main__":
    unittest.main()
