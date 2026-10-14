#!/usr/bin/env python3
"""
Pipecrawler - Radxa side of the RP2040 UART link.

Pings the RP2040, then prints the encoder counts it streams.  With --drive it
runs both motors for a few seconds and stops.

    sudo apt install python3-serial
    python3 uart_link.py                       # monitor, default /dev/ttyS4
    python3 uart_link.py --zero                # reset counts first
    python3 uart_link.py --drive 50 50 3       # both treads forward 50% for 3 s

Needs the UART4-M1 overlay enabled in `sudo rsetup` (Overlays), then a reboot,
and your user in the dialout group: `sudo usermod -aG dialout $USER`, re-login.
Wiring: Radxa pin 16 (RX) <- RP2040 GP0, pin 18 (TX) -> RP2040 GP1, pin 6 GND.
Protocol is documented in running/rp2040/main.py.
"""

import argparse
import sys
import time

import serial

KEEPALIVE_S = 0.1       # RP2040 watchdog trips after 0.5 s of silence


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port", nargs="?", default="/dev/ttyS4")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--zero", action="store_true", help="reset counts first")
    ap.add_argument("--drive", nargs=3, type=float, metavar=("LEFT", "RIGHT", "SECONDS"),
                    help="drive treads at LEFT/RIGHT duty (-100..100, + = forward) for SECONDS, then stop")
    args = ap.parse_args()

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.5)
    except serial.SerialException as e:
        if e.errno == 13:
            hint = ("permission denied - run: sudo usermod -aG dialout $USER, "
                    "then log out and back in")
        else:
            hint = "is the UART4-M1 overlay enabled in rsetup?"
        sys.exit("cannot open %s: %s\n(%s)" % (args.port, e, hint))

    ser.reset_input_buffer()
    ser.write(b"PING\n")
    deadline = time.time() + 2
    while time.time() < deadline:
        line = ser.readline().strip()
        if line == b"PONG":
            print("link OK - RP2040 answered PING")
            break
    else:
        sys.exit("no PONG within 2 s. Check: TX/RX not swapped, shared GND, "
                 "RP2040 powered and running main.py")

    if args.zero or args.drive:
        ser.write(b"ZERO\n")

    drive_until = None
    if args.drive:
        d1, d2, secs = int(args.drive[0]), int(args.drive[1]), args.drive[2]
        drive_cmd = b"M %d %d\n" % (d1, d2)
        drive_until = time.time() + secs
        print("driving left=%+d%% right=%+d%% for %.1f s" % (d1, d2, secs))

    print("     ms        left       right  duty_l duty_r")
    last_print = 0
    last_send = 0
    try:
        while True:
            if drive_until is not None:
                if time.time() >= drive_until:
                    ser.write(b"STOP\n")
                    drive_until = None
                    print("stopped - Ctrl-C to exit, counts keep streaming")
                elif time.time() - last_send >= KEEPALIVE_S:
                    ser.write(drive_cmd)
                    last_send = time.time()

            line = ser.readline().decode("ascii", "replace").strip()
            if not line:
                print("(no data for 0.5 s)")
                continue
            parts = line.split()
            if parts[0] == "E" and len(parts) == 6:
                if time.time() - last_print >= 0.2:     # 5 lines/s is readable
                    last_print = time.time()
                    print("%9s  %+10d  %+10d   %+4d   %+4d" % (
                        parts[1], int(parts[2]), int(parts[3]),
                        int(parts[4]), int(parts[5])))
            else:
                print("<<", line)
    finally:
        ser.write(b"STOP\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
