import unittest
from whack.protocol import Hello, Range, measure, parse


class ProtocolTests(unittest.TestCase):
    def test_roundtrip(self):
        self.assertEqual(parse(b"WM1 HELLO 0"),Hello(0))
        self.assertEqual(parse(b"WM1 RANGE 1 4294967295 180000 2000 OK\n"),Range(1,4294967295,180000,2000,"OK"))
        self.assertEqual(measure(1,90000),b"WM1 MEASURE 1 90000")

    def test_reject_malformed_and_invalid(self):
        packets = [b"",b"WM2 HELLO 0",b"WM1 HELLO 2",b"WM1 HELLO 0 EXTRA",b"\xff",b"x"*129,
                   b"WM1 RANGE 0 1 90000 0 OK",b"WM1 RANGE 0 1 90000 50 TIMEOUT",
                   b"WM1 RANGE 0 0 90000 50 OK",b"WM1 RANGE 0 4294967296 90000 50 OK",
                   b"WM1 RANGE 0 1 -1 50 OK",b"WM1 RANGE 0 1 180001 50 OK",
                   b"WM1 RANGE 0 1 90000 9999 OK",b"WM1 RANGE 0 1 90000 50 OK\x00"]
        for packet in packets:
            with self.subTest(packet=packet):
                with self.assertRaises(ValueError): parse(packet)


if __name__ == "__main__": unittest.main()
