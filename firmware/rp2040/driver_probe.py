r"""
Pipecrawler - TB6612 output probe (MicroPython, RP2040-Zero)

Diagnostic for "motor does not spin".  Holds the driver in a static full-on
state (no PWM chopping) so the outputs can be measured with a multimeter.

Requires VM = 12V connected.  Cycles forward / off / reverse / off.

Probe AO1 (pin 12) and AO2 (pin 13) against GND:

    forward   AO1 ~12V   AO2 ~0V
    reverse   AO1 ~0V    AO2 ~12V
    off       both ~0V

If the outputs swing correctly the driver and its wiring are fine, and the
fault is between AO1/AO2 and the motor.  If they never swing, the driver is not
being enabled or VM is not reaching it - check VM at pin 9, VCC at pin 10, and
that all three GND pins are tied to the star ground.

If the motor is connected and the driver works, it will spin during this - that
by itself answers the question.

    python3 -m mpremote connect COM6 run firmware\rp2040\driver_probe.py
"""

import time

from machine import Pin

PIN_PWMA = 2
PIN_AIN1 = 3
PIN_AIN2 = 4
PIN_STBY = 8

DRIVE_S = 5
PAUSE_S = 2


def main():
    pwma = Pin(PIN_PWMA, Pin.OUT, value=0)
    ain1 = Pin(PIN_AIN1, Pin.OUT, value=0)
    ain2 = Pin(PIN_AIN2, Pin.OUT, value=0)
    stby = Pin(PIN_STBY, Pin.OUT, value=0)

    print("TB6612 output probe - VM must be connected (12V).")
    print("Probe AO1 (pin 12) and AO2 (pin 13) against GND.")
    print("Ctrl-C to stop.")
    print()

    try:
        stby.value(1)
        pwma.value(1)            # full on, no chopping

        while True:
            ain1.value(1); ain2.value(0)
            print("  forward  - expect AO1 ~12V, AO2 ~0V")
            time.sleep(DRIVE_S)

            ain1.value(0); ain2.value(0)
            print("  off      - expect both ~0V")
            time.sleep(PAUSE_S)

            ain1.value(0); ain2.value(1)
            print("  reverse  - expect AO1 ~0V, AO2 ~12V")
            time.sleep(DRIVE_S)

            ain1.value(0); ain2.value(0)
            print("  off      - expect both ~0V")
            time.sleep(PAUSE_S)

    except KeyboardInterrupt:
        pass
    finally:
        pwma.value(0)
        ain1.value(0)
        ain2.value(0)
        stby.value(0)
        print()
        print("stopped - driver disabled")


main()
