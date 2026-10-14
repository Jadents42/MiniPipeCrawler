"""
Pipecrawler - hand-turn encoder readout (MicroPython, RP2040-Zero)

Live count, printed the moment it changes.  No motor power needed - this is the
safest way to confirm the encoder works and to measure counts per revolution.

Reuses the PIO decoder from encoder_test.py.  Ctrl-C prints a summary.

    python -m mpremote connect COM6 run hand_test.py
"""

import time

import rp2
from machine import Pin

from encoder_test import PIN_A, PIN_B, PIO_FREQ, quadrature_2x, read_count

POLL_MS = 20


def main():
    pin_a = Pin(PIN_A, Pin.IN, Pin.PULL_UP)
    pin_b = Pin(PIN_B, Pin.IN, Pin.PULL_UP)

    sm = rp2.StateMachine(0, quadrature_2x, freq=PIO_FREQ,
                          in_base=pin_b, jmp_pin=pin_a)
    sm.exec("set(x, 0)")
    sm.active(1)

    zero = read_count(sm)
    last = 0
    gross = 0          # total travel, counting reversals
    lo = hi = 0

    print("turn the output shaft - Ctrl-C to stop")
    print()
    print("   count    delta   dir    A B")
    print("  " + "-" * 30)

    try:
        while True:
            count = read_count(sm) - zero
            if count != last:
                delta = count - last
                gross += abs(delta)
                lo = min(lo, count)
                hi = max(hi, count)
                print("  %+6d   %+6d   %s   %d %d" % (
                    count, delta,
                    "fwd" if delta > 0 else "rev",
                    pin_a.value(), pin_b.value()))
                last = count
            time.sleep_ms(POLL_MS)

    except KeyboardInterrupt:
        sm.active(0)
        print()
        print("final count : %+d" % last)
        print("total travel: %d counts (includes any back-and-forth)" % gross)
        print("range       : %+d .. %+d" % (lo, hi))
        if gross:
            print("coherence   : %.1f%%  (100%% = no reversals)"
                  % (abs(last) / gross * 100.0))
        print()
        print("For counts-per-rev: mark the shaft, turn exactly one full")
        print("output revolution one way, and read 'final count'.")


main()
