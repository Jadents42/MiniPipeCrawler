r"""
Pipecrawler - TB6612 brake test (MicroPython, RP2040-Zero)

Diagnostic for "motor does not spin", using no test equipment.

The TB6612 truth table has a short-brake state: with IN1 and IN2 both HIGH the
motor terminals are shorted together through the low-side FETs, which makes the
shaft markedly harder to turn.  With both LOW the outputs go high-impedance and
it spins freely.

So: alternate the two states while spinning the rear disc by hand at roughly
even effort.  The encoder counts each phase.  Far fewer counts during BRAKE
proves, in one shot, that VM is present, the driver is enabled, and the motor
really is connected to AO1/AO2 - none of which needs a meter.

Requires 12V on VM.  Run with the motor connected to the driver as normal.

    python3 -m mpremote connect COM6 run firmware\rp2040\brake_test.py
"""

import time

import rp2
from machine import Pin

from encoder_test import PIN_A, PIN_B, PIO_FREQ, quadrature_2x, read_count

PIN_PWMA = 2
PIN_AIN1 = 3
PIN_AIN2 = 4
PIN_STBY = 8

PHASE_S = 6


def main():
    pin_a = Pin(PIN_A, Pin.IN, Pin.PULL_UP)
    pin_b = Pin(PIN_B, Pin.IN, Pin.PULL_UP)

    sm = rp2.StateMachine(0, quadrature_2x, freq=PIO_FREQ,
                          in_base=pin_b, jmp_pin=pin_a)
    sm.exec("set(x, 0)")
    sm.active(1)

    pwma = Pin(PIN_PWMA, Pin.OUT, value=1)
    ain1 = Pin(PIN_AIN1, Pin.OUT, value=0)
    ain2 = Pin(PIN_AIN2, Pin.OUT, value=0)
    stby = Pin(PIN_STBY, Pin.OUT, value=1)

    print("Brake test - spin the black disc on the back of the motor")
    print("continuously, at about the same effort throughout.")
    print("Ctrl-C when you have a few rounds.")
    print()

    coast_total = brake_total = 0
    rounds = 0

    try:
        while True:
            for label, a1, a2 in (("COAST", 0, 0), ("BRAKE", 1, 1)):
                ain1.value(a1)
                ain2.value(a2)

                print("  %s - spin now..." % label, end="")
                start = read_count(sm)
                time.sleep(PHASE_S)
                moved = abs(read_count(sm) - start)
                print("  %d counts" % moved)

                if label == "COAST":
                    coast_total += moved
                else:
                    brake_total += moved
                    rounds += 1

    except KeyboardInterrupt:
        pass
    finally:
        ain1.value(0)
        ain2.value(0)
        pwma.value(0)
        stby.value(0)
        sm.active(0)

        print()
        if not rounds:
            print("no complete rounds - run it longer")
            return

        print("coast total: %d counts" % coast_total)
        print("brake total: %d counts" % brake_total)
        print()

        if coast_total < 50:
            print("Barely any counts either way - you were not turning it, or")
            print("the encoder is not reading.  Check hand_test.py first.")
        elif brake_total < coast_total * 0.6:
            print("BRAKE is clearly stiffer.  That proves VM is present, the")
            print("driver is enabled, and the motor IS connected to AO1/AO2.")
            print("The fault is then in PWM or direction control, not wiring.")
        else:
            print("No real difference between the two states.  The driver is")
            print("not gripping the motor, so one of these is true:")
            print("  - 12V is not reaching VM (pin 9)")
            print("  - PSU negative is not tied to the TB6612 GND pins")
            print("  - the motor is not on AO1/AO2 (pins 12/13)")
            print("Note pins 12-15 run A01, A02, B02, B01 - B02 comes BEFORE")
            print("B01, so it is easy to land the motor on the B channel by")
            print("miscounting.  Channel B is not driven by this test.")


main()
