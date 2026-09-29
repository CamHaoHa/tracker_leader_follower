"""Bench one sensor/servo: python -m tools.probe_node --help."""
import argparse
import math
import socket
import statistics
import time
from whack.protocol import MAX_BUZZ_MS, MAX_PACKET, MAX_SEQUENCE, Range, buzz, measure, parse


def main(argv=None):
    parser = argparse.ArgumentParser(description="Point one sensor at a fixed bearing and print repeated ranges")
    parser.add_argument("--ip", required=True, help="Node IPv4 address from USB serial")
    parser.add_argument("--node", required=True, type=int, choices=range(10), metavar="{0..9}")
    parser.add_argument("--angle", type=float, default=90, help="Logical degrees; 90 faces away from the wall")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--buzz", action="store_true",
                        help="Sound the box's buzzer throughout (middle box). Compare the ranges with a "
                             "run without it to check that the sound does not disturb the sensor")
    args = parser.parse_args(argv)
    if not math.isfinite(args.angle) or not 0 <= args.angle <= 180 or not 1 <= args.count <= 1000:
        parser.error("Angle must be 0..180 and count 1..1000")
    try:
        socket.inet_aton(args.ip)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(("0.0.0.0", 4210))
            address = (args.ip, 4211)
            sequence = int(time.time()*1000) & MAX_SEQUENCE or 1
            angle = round(args.angle*1000)
            distances = []
            print("sequence,angle_deg,distance_mm,status")
            for _ in range(args.count):
                if args.buzz:
                    # Renewed before every ping, so the sound never lapses; the
                    # box stops by itself 2 s after the last one.
                    sock.sendto(buzz(MAX_BUZZ_MS), address)
                sequence = sequence % MAX_SEQUENCE + 1
                sock.sendto(measure(sequence, angle), address)
                deadline = time.monotonic()+1.0
                reply = None
                while time.monotonic() < deadline:
                    sock.settimeout(max(.001, deadline-time.monotonic()))
                    try:
                        data, source = sock.recvfrom(MAX_PACKET+1)
                    except (socket.timeout, ConnectionResetError):
                        break
                    try:
                        message = parse(data)
                    except ValueError:
                        continue
                    if (source == address and isinstance(message, Range) and message.node == args.node
                            and message.seq == sequence and (message.status != "OK" or message.angle_mdeg == angle)):
                        reply = message
                        break
                if reply is None:
                    print(f"{sequence},{args.angle},,NO_REPLY", flush=True)
                else:
                    print(f"{sequence},{reply.angle_mdeg/1000},{reply.distance_mm},{reply.status}", flush=True)
                    if reply.status == "OK":
                        distances.append(reply.distance_mm)
                time.sleep(.1)
            if args.buzz:
                sock.sendto(buzz(0), address)
            if distances:
                print(f"Valid: {len(distances)}/{args.count}; median: {statistics.median(distances):.1f} mm; "
                      f"range: {min(distances)}..{max(distances)} mm")
                return 0
            return 1
    except OSError as exc:
        parser.exit(2, f"Probe failed: {exc}. Close the visualizer and other controllers first.\n")


if __name__ == "__main__":
    raise SystemExit(main())
