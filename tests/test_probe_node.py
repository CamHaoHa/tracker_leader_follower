"""The bench probe against a stand-in node on loopback (UDP 4210 must be free)."""

import contextlib
import io
import re
import socket
import threading
import time
import unittest

from tools import probe_node


class FakeNode:
    """Answers WM1 MEASURE with a fixed range and records every datagram."""

    def __init__(self, ip="127.0.0.2"):
        self.address = (ip, 4211)
        self.received = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(self.address)
        self.sock.settimeout(.05)
        self.running = True
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while self.running:
            try:
                data, source = self.sock.recvfrom(256)
            except socket.timeout:
                continue
            except OSError:
                return
            self.received.append((data, source))
            match = re.fullmatch(rb"WM1 MEASURE ([0-9]+) ([0-9]+)", data)
            if match:
                self.sock.sendto(b"WM1 RANGE 1 %s %s 800 OK" % (match[1], match[2]), source)

    def close(self):
        self.running = False
        self.thread.join(timeout=1)
        self.sock.close()


class ProbeNodeTests(unittest.TestCase):
    def setUp(self):
        self.node = FakeNode()
        self.addCleanup(self.node.close)

    def probe(self, *extra, datagrams):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = probe_node.main(["--ip", self.node.address[0], "--node", "1", "--count", "3", *extra])
        self.assertEqual(code, 0, output.getvalue())
        self.assertIn("Valid: 3/3; median: 800.0 mm", output.getvalue())
        deadline = time.monotonic() + 1          # the last datagram is read by the node's thread
        while len(self.node.received) < datagrams and time.monotonic() < deadline:
            time.sleep(.01)
        time.sleep(.1)                           # ...and nothing may follow it
        self.assertEqual({source for _, source in self.node.received}, {("127.0.0.1", 4210)})
        return [b" ".join(data.split()[:2]) if data.startswith(b"WM1 MEASURE") else data
                for data, _ in self.node.received]

    def test_a_plain_probe_never_sounds_the_buzzer(self):
        self.assertEqual(self.probe(datagrams=3), [b"WM1 MEASURE"]*3)

    def test_buzz_renews_the_sound_before_every_ping_and_silences_it_at_the_end(self):
        self.assertEqual(self.probe("--buzz", datagrams=7),
                         [b"WM2 BUZZ 2000", b"WM1 MEASURE"]*3 + [b"WM2 BUZZ 0"])


if __name__ == "__main__":
    unittest.main()
