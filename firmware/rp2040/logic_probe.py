r"""
Pipecrawler - logic probe (MicroPython, RP2040-Zero)

Verifies control wiring end to end without a multimeter, by using a spare GPIO
as a digital voltmeter.

Drives one control line HIGH at a time, exactly like driver_check.py, while
reading PROBE_PIN and showing its state live.  Clip a jumper from PROBE_PIN to
a TB6612 control pin: it should read HIGH only during that pin's phase.  That
confirms continuity AND correct mapping in one pass.

    ############################################################
    #  PROBE_PIN tolerates 0-3.3V ONLY.                        #
    #  NEVER touch it to VM (pin 9), AO1 (12) or AO2 (13).     #
    #  12V on a GPIO destroys the RP2040.                      #
    #  Safe to probe: pins 1-4 (PWMA/AIN2/AIN1/STBY) and 10.   #
    #  A 1k resistor in series is cheap insurance.             #
    ############################################################

    python3 -m mpremote connect COM6 run firmware\rp2040\logic_probe.py
"""

import time

from machine import Pin

# Spare GPIO used as the probe tip.  On the RP2040-Zero the silkscreen number IS
# the GP number - a pad marked 15 is GP15.  Other free pads: GP12, GP13, GP14,
# GP27, GP28, GP29.  Do NOT use GP16 (onboard RGB LED).
PROBE_PIN = 15
HOLD_S = 4

CONTROL = (
    ("PWMA", 2, "TB6612 pin 1"),
    ("AIN2", 4, "TB6612 pin 2"),
    ("AIN1", 3, "TB6612 pin 3"),
    ("STBY", 8, "TB6612 pin 4"),
)


def main():
    probe = Pin(PROBE_PIN, Pin.IN, Pin.PULL_DOWN)
    pins = {name: Pin(gp, Pin.OUT, value=0) for name, gp, _ in CONTROL}

    print("Logic probe - jumper from GP%d to a TB6612 control pin." % PROBE_PIN)
    print("NEVER probe VM, AO1 or AO2.  3.3V maximum.")
    print()
    print("The probed pin should read HIGH only during its own phase.")
    print("Ctrl-C to stop.")
    print()

    try:
        while True:
            for name, gp, where in CONTROL:
                for other in pins.values():
                    other.value(0)
                pins[name].value(1)

                # sample the probe across the phase
                t0 = time.ticks_ms()
                seen = set()
                while time.ticks_diff(time.ticks_ms(), t0) < HOLD_S * 1000:
                    seen.add(probe.value())
                    time.sleep_ms(20)

                if seen == {1}:
                    state = "HIGH"
                elif seen == {0}:
                    state = "low"
                else:
                    state = "UNSTABLE (floating?)"

                print("  driving %-5s (GP%-2d -> %-14s)   probe reads %s"
                      % (name, gp, where, state))
    except KeyboardInterrupt:
        for p in pins.values():
            p.value(0)
        print()
        print("stopped - control lines low")
        print()
        print("Expected: probe reads HIGH in exactly one phase - the pin it is")
        print("clipped to.  Always low means that wire is open.  HIGH in more")
        print("than one phase means two control wires are shorted together.")


main()
