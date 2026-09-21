r"""
Pipecrawler - counts per motor revolution (MicroPython, RP2040-Zero)

Spin the black disc on the BACK of the motor.  That is the motor shaft, ahead of
the worm reduction, so one spin is one motor revolution - no cranking through the
gearbox.  Counts per motor revolution is what the control loop uses; the output
shaft figure is just this times the gearbox ratio, which you read off the
product listing.

Hands-free: spin the disc TURNS_PER_TRIAL times, stop, hold still, and the trial
reports itself.  Repeat for as many trials as you like.  Ctrl-C for the summary.

    python3 -m mpremote connect COM6 run firmware\rp2040\cpr_test.py
"""

import time

import rp2
from machine import Pin

from encoder_test import PIN_A, PIN_B, PIO_FREQ, quadrature_2x, read_count

TURNS_PER_TRIAL = 1     # spins of the rear disc per trial
#
# The disc is small and stiff, and this measures NET displacement, so any
# slip or back-and-forth cancels out and undercounts.  One deliberate,
# clean revolution beats ten sloppy ones.  Expect an even number - this
# decoder counts both edges of A, so counts per rev is always 2 x PPR.
POLL_MS = 20
SETTLE_MS = 1500        # stillness that ends a trial
MIN_COUNTS = 6          # ignore the +/-1 resting dither


def main():
    pin_a = Pin(PIN_A, Pin.IN, Pin.PULL_UP)
    pin_b = Pin(PIN_B, Pin.IN, Pin.PULL_UP)

    sm = rp2.StateMachine(0, quadrature_2x, freq=PIO_FREQ,
                          in_base=pin_b, jmp_pin=pin_a)
    sm.exec("set(x, 0)")
    sm.active(1)

    zero = read_count(sm)
    last = base = 0
    last_change = time.ticks_ms()
    trials = []

    print("Spin the black disc on the back of the motor %d times," % TURNS_PER_TRIAL)
    print("then stop and hold still.  Each trial reports after %.1fs."
          % (SETTLE_MS / 1000))
    print("Ctrl-C when you have a few.")
    print()

    try:
        while True:
            count = read_count(sm) - zero
            now = time.ticks_ms()

            if count != last:
                last = count
                last_change = now
            elif time.ticks_diff(now, last_change) > SETTLE_MS:
                moved = abs(last - base)
                if moved >= MIN_COUNTS:
                    trials.append(moved)
                    print("trial %d: %4d counts over %d turns  ->  %.1f per motor rev"
                          % (len(trials), moved, TURNS_PER_TRIAL,
                             moved / TURNS_PER_TRIAL))
                base = last
                last_change = now

            time.sleep_ms(POLL_MS)

    except KeyboardInterrupt:
        sm.active(0)
        print()
        if not trials:
            print("no trials recorded")
            return

        per_rev = sum(trials) / len(trials) / TURNS_PER_TRIAL
        spread = (max(trials) - min(trials)) / TURNS_PER_TRIAL
        print("%d trials, mean %.2f counts per motor revolution (spread %.2f)"
              % (len(trials), per_rev, spread))

        # This decoder counts both edges of A only, so counts = 2 x PPR.
        ppr = per_rev / 2
        print("implies %.1f pulses per revolution per channel" % ppr)
        if abs(ppr - round(ppr)) < 0.15 and round(ppr) > 0:
            print("  -> almost certainly a %d PPR encoder" % round(ppr))
        else:
            print("  -> not landing on a whole number; try more turns per trial")
        print()
        print("Output-shaft counts = %.0f x gearbox ratio." % per_rev)
        print("Put that in COUNTS_PER_OUTPUT_REV in encoder_test.py for the RPM column.")


main()
