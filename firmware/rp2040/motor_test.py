r"""
Pipecrawler - Motor 1 closed-loop-ready driver test (MicroPython, RP2040-Zero)

Ramps PWM in both directions and reports commanded duty against measured
encoder rate, plus coherence at every step.

Coherence is the point of this test.  Bring-up on 2026-09-21 measured 100%
across 3V/6V/12V, but that was steady DC from a bench supply.  This is the first
run with the TB6612 chopping current, which is a far harsher electrical
environment.  Any drop from 100% here is PWM noise reaching the encoder lines.

Prerequisites: VM = 12V, VCC = 3.3V, all three TB6612 GND pins tied to the star
ground.  Run driver_check.py first to verify the control wiring.

    python3 -m mpremote connect COM6 run firmware\rp2040\motor_test.py
"""

import time

import rp2
from machine import PWM, Pin

from encoder_test import PIN_A, PIN_B, PIO_FREQ, quadrature_2x, read_count

PIN_PWMA = 2
PIN_AIN1 = 3
PIN_AIN2 = 4
PIN_STBY = 8

PWM_HZ = 20_000          # above audible; well inside the TB6612's range
STEPS = (20, 40, 60, 80, 100)
SETTLE_MS = 1200         # let speed stabilise before measuring
MEASURE_MS = 1500
SAMPLE_MS = 20


def measure(sm):
    """Net and gross count rates over MEASURE_MS."""
    t0 = time.ticks_ms()
    start = last = read_count(sm)
    gross = 0

    while time.ticks_diff(time.ticks_ms(), t0) < MEASURE_MS:
        time.sleep_ms(SAMPLE_MS)
        now = read_count(sm)
        gross += abs(now - last)
        last = now

    elapsed = time.ticks_diff(time.ticks_ms(), t0)
    net = last - start
    return net * 1000.0 / elapsed, gross * 1000.0 / elapsed


def run_direction(sm, pwm, ain1, ain2, label, a1, a2):
    ain1.value(a1)
    ain2.value(a2)

    print()
    print("%s  (AIN1=%d AIN2=%d)" % (label, a1, a2))
    print("  duty     net/s   counts/s   coherence")
    print("  " + "-" * 38)

    for duty in STEPS:
        pwm.duty_u16(int(65535 * duty / 100))
        time.sleep_ms(SETTLE_MS)
        net_rate, gross_rate = measure(sm)
        coherence = (abs(net_rate) / gross_rate * 100.0) if gross_rate else 100.0
        print("  %3d%%  %+8.1f   %8.1f      %5.1f%%"
              % (duty, net_rate, gross_rate, coherence))

    pwm.duty_u16(0)
    time.sleep_ms(1500)      # coast down before reversing


def main():
    pin_a = Pin(PIN_A, Pin.IN, Pin.PULL_UP)
    pin_b = Pin(PIN_B, Pin.IN, Pin.PULL_UP)

    sm = rp2.StateMachine(0, quadrature_2x, freq=PIO_FREQ,
                          in_base=pin_b, jmp_pin=pin_a)
    sm.exec("set(x, 0)")
    sm.active(1)

    ain1 = Pin(PIN_AIN1, Pin.OUT, value=0)
    ain2 = Pin(PIN_AIN2, Pin.OUT, value=0)
    stby = Pin(PIN_STBY, Pin.OUT, value=0)

    pwm = PWM(Pin(PIN_PWMA))
    pwm.freq(PWM_HZ)
    pwm.duty_u16(0)

    print("Motor 1 driver test - PWM %d Hz on GP%d" % (PWM_HZ, PIN_PWMA))
    print("Watch coherence: 100%% means PWM noise is not reaching the encoder.")

    try:
        stby.value(1)        # enable the driver
        run_direction(sm, pwm, ain1, ain2, "direction A", 1, 0)
        run_direction(sm, pwm, ain1, ain2, "direction B", 0, 1)

        print()
        print("Sign of net/s tells you which direction is positive.")
        print("Direction A should be one sign and B the other; if both read the")
        print("same sign, AIN1 and AIN2 are swapped or one is not connected.")

    finally:
        pwm.duty_u16(0)
        pwm.deinit()
        ain1.value(0)
        ain2.value(0)
        stby.value(0)        # driver back to standby
        sm.active(0)
        print()
        print("stopped - PWM off, STBY low, driver disabled")


main()
