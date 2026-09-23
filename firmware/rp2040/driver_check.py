r"""
Pipecrawler - TB6612 control-line check (MicroPython, RP2040-Zero)

Run this BEFORE connecting 12V to VM.

Drives one control line high at a time while holding the rest low, so you can
probe the TB6612 end with a multimeter and confirm every wire lands where you
think it does.  Catches swapped AIN1/AIN2 or an off-by-one on the header while
a mistake still costs nothing.

Only VCC (3.3V) needs to be connected for this.  With VM absent the outputs
cannot drive anything, so nothing can move and nothing can be damaged.

    python3 -m mpremote connect COM6 run firmware\rp2040\driver_check.py
"""

import time

from machine import Pin

HOLD_S = 6

# name, RP2040 GPIO, where to probe on the driver
CONTROL = (
    ("PWMA", 2, "TB6612 pin 1  (PWMA)"),
    ("AIN2", 4, "TB6612 pin 2  (AIN2)"),
    ("AIN1", 3, "TB6612 pin 3  (AIN1)"),
    ("STBY", 8, "TB6612 pin 4  (STBY)"),
)


def main():
    pins = {name: Pin(gp, Pin.OUT, value=0) for name, gp, _ in CONTROL}

    print("TB6612 control-line check - VM must NOT be connected.")
    print("Black probe on TB6612 GND (pin 8, 11 or 16).")
    print("Red probe on the pin named below: expect ~3.3V there, ~0V on the")
    print("other three.  Ctrl-C to stop.")
    print()

    try:
        while True:
            for name, gp, where in CONTROL:
                for other in pins.values():
                    other.value(0)
                pins[name].value(1)

                print("  %s HIGH  (GP%d)  ->  probe %s" % (name, gp, where))
                time.sleep(HOLD_S)
    except KeyboardInterrupt:
        for p in pins.values():
            p.value(0)
        print()
        print("all control lines returned low")


main()
