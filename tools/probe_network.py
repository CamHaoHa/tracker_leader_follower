"""Check laptop-to-ESP32 UDP replies without operating sensors or servos."""
import argparse
import ipaddress
import secrets
import socket
import statistics
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", required=True, type=ipaddress.IPv4Address)
    args = parser.parse_args()
    target = (str(args.ip), 4211)
    timings = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("0.0.0.0", 4210))
            for attempt in range(1, 6):
                token = secrets.token_hex(8)
                expected = f"WMNET PONG 0 {token}".encode()
                started = time.monotonic()
                sock.sendto(f"WMNET PING {token}".encode(), target)
                deadline = started + 2
                matched = False
                while time.monotonic() < deadline:
                    sock.settimeout(max(0.001, deadline - time.monotonic()))
                    try:
                        data, sender = sock.recvfrom(256)
                    except (socket.timeout, ConnectionResetError):
                        break
                    if sender == target and data == expected:
                        elapsed = (time.monotonic() - started) * 1000
                        timings.append(elapsed)
                        print(f"PASS {attempt}/5: left ESP32 replied in {elapsed:.1f} ms", flush=True)
                        matched = True
                        break
                if not matched:
                    print(f"NO REPLY {attempt}/5", flush=True)
                time.sleep(0.2)
    except OSError as error:
        parser.exit(2, f"UDP test failed: {error}. Close other tracker tools using UDP 4210.\n")
    print(f"UDP replies: {len(timings)}/5")
    if timings:
        print(f"Average round trip: {statistics.mean(timings):.1f} ms")
    return 0 if len(timings) == 5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
