import unittest
from unittest.mock import Mock, patch
from whack.transport import UdpTransport


class TransportTests(unittest.TestCase):
    def test_configured_ips_survive_discovery_timeout(self):
        now=[0]
        with patch("whack.transport.socket.socket",return_value=Mock()):
            t=UdpTransport(lambda:now[0],node_ips=["192.168.0.10","192.168.0.11"])
            now[0]=100
            self.assertEqual(t.address(0),("192.168.0.10",4211))
            self.assertEqual(t.address(1),("192.168.0.11",4211))

    def test_conflicting_discovered_node_is_not_used(self):
        now=[0]
        s=Mock();s.recvfrom.side_effect=[(b"WM1 HELLO 0",("192.168.0.10",4211)),
                                       (b"WM1 HELLO 0",("192.168.0.11",4211)),BlockingIOError()]
        with patch("whack.transport.socket.socket",return_value=s):
            t=UdpTransport(lambda:now[0]);t.receive()
            self.assertIsNone(t.address(0))


if __name__ == "__main__": unittest.main()
