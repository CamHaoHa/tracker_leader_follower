import unittest
from whack.protocol import Hello, Range, Ready, aim, buzz, fire, measure, parse


class ProtocolTests(unittest.TestCase):
    def test_legacy_roundtrip(self):
        self.assertEqual(parse(b"WM1 HELLO 0"), Hello(0))
        self.assertEqual(parse(b"WM1 RANGE 1 4294967295 180000 2000 OK\n"),
                         Range(1, 4294967295, 180000, 2000, "OK"))
        self.assertEqual(measure(1, 90000), b"WM1 MEASURE 1 90000")

    def test_coordinated_protocol(self):
        self.assertEqual(parse(b"WM2 HELLO 1"), Hello(1, version=2))
        self.assertEqual(aim(12, 57000), b"WM2 AIM 12 57000")
        self.assertEqual(fire(12), b"WM2 FIRE 12")
        self.assertEqual(parse(b"WM2 READY 0 12 57000 1000 OK"), Ready(0, 12, 57000, 1000, "OK"))
        self.assertEqual(parse(b"WM2 READY 0 12 57000 0 INVALID"), Ready(0, 12, 57000, 0, "INVALID"))
        self.assertEqual(parse(b"WM2 RANGE 1 12 123000 1500 OK 4294967295 8750"),
                         Range(1, 12, 123000, 1500, "OK", 4294967295, 8750, 2))
        self.assertEqual(parse(b"WM2 RANGE 1 12 123000 0 TIMEOUT 0 25000").age_us, 25000)

    def test_reject_malformed_and_invalid(self):
        packets = [b"", b"WM3 HELLO 0", b"WM1 HELLO 10", b"WM1 HELLO 0 EXTRA", b"\xff", b"x"*129,
                   b"WM1 RANGE 0 1 90000 0 OK", b"WM1 RANGE 0 1 90000 50 TIMEOUT",
                   b"WM1 RANGE 0 0 90000 50 OK", b"WM1 RANGE 0 4294967296 90000 50 OK",
                   b"WM1 RANGE 0 1 -1 50 OK", b"WM1 RANGE 0 1 180001 50 OK",
                   b"WM1 RANGE 0 1 90000 9999 OK", b"WM1 RANGE 0 1 90000 50 OK\x00",
                   b"WM2 RANGE 0 1 90000 50 OK", b"WM1 RANGE 0 1 90000 50 OK 0 0",
                   b"WM2 RANGE 0 1 90000 50 OK 0", b"WM2 RANGE 0 1 90000 50 OK 4294967296 0",
                   b"WM2 RANGE 0 1 90000 50 OK 0 4294967296", b"WM2 RANGE 0 1 90000 50 OK -1 0",
                   b"WM2 READY 0 1 90000 0 OK", b"WM2 READY 0 1 90000 1001 OK",
                   b"WM2 READY 0 1 90000 1 INVALID", b"WM2 READY 0 1 90000 1000 TIMEOUT",
                   b"WM2 READY 0 0 90000 1000 OK", b"WM2 READY 0 1 180001 1000 OK"]
        for packet in packets:
            with self.subTest(packet=packet), self.assertRaises(ValueError):
                parse(packet)

    def test_command_values_are_bounded_integers(self):
        for seq in (0, -1, 4294967296, 1.5, True):
            with self.subTest(seq=seq), self.assertRaises(ValueError):
                fire(seq)
        for angle in (-1, 180001, 90.0, False):
            with self.subTest(angle=angle), self.assertRaises(ValueError):
                aim(1, angle)

    def test_buzz_duration_is_a_bounded_integer(self):
        self.assertEqual(buzz(400), b"WM2 BUZZ 400")
        self.assertEqual(buzz(0), b"WM2 BUZZ 0")          # silence at once
        self.assertEqual(buzz(2000), b"WM2 BUZZ 2000")    # the firmware's limit
        for duration in (-1, 2001, 4294967296, 400.0, "400", None, True, False):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                buzz(duration)

    def test_buzz_is_a_command_not_a_message_from_a_box(self):
        with self.assertRaises(ValueError):
            parse(buzz(400))


if __name__ == "__main__":
    unittest.main()
