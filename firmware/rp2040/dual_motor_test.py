r"""
Pipecrawler - both motors (MicroPython, RP2040-Zero)

Three passes:
  1. Motor 2 alone, both directions - mirrors what motor_test.py did for Motor 1
  2. Both together at matched duty - the speed-matching check
  3. Opposed directions - confirms independent control

Each motor gets its own PIO state machine; MicroPython reuses the program
offset, so both share one copy of the decoder in PIO instruction memory.

STBY is shared and enables both channels.

    python3 -m mpremote connect COM6 run firmware\rp2040\dual_motor_test.py
"""

import time

import rp2
from machine import PWM, Pin

from encoder_test import PIO_FREQ, quadrature_2x, read_count

PIN_STBY = 8
PWM_HZ = 20_000

# 10% included to find where the dead zone ends
STEPS = (10, 20, 40, 60, 80, 100)
SETTLE_MS = 1200
MEASURE_MS = 1500
SAMPLE_MS = 20


class Motor:
    def __init__(self, name, pin_pwm, pin_in1, pin_in2, enc_a, enc_b, sm_id):
        self.name = name
        self.in1 = Pin(pin_in1, Pin.OUT, value=0)
        self.in2 = Pin(pin_in2, Pin.OUT, value=0)
        self.pwm = PWM(Pin(pin_pwm))
        self.pwm.freq(PWM_HZ)
        self.pwm.duty_u16(0)

        a = Pin(enc_a, Pin.IN, Pin.PULL_UP)
        b = Pin(enc_b, Pin.IN, Pin.PULL_UP)
        self.sm = rp2.StateMachine(sm_id, quadrature_2x, freq=PIO_FREQ,
                                   in_base=b, jmp_pin=a)
        self.sm.exec("set(x, 0)")
        self.sm.active(1)

    def direction(self, forward):
        self.in1.value(1 if forward else 0)
        self.in2.value(0 if forward else 1)

    def duty(self, pct):
        self.pwm.duty_u16(int(65535 * pct / 100))

    def coast(self):
        self.pwm.duty_u16(0)
        self.in1.value(0)
        self.in2.value(0)

    def shutdown(self):
        self.coast()
        self.pwm.deinit()
        self.sm.active(0)


def measure(motors):
    """Net and gross rates for each motor over one shared window."""
    t0 = time.ticks_ms()
    start = [read_count(m.sm) for m in motors]
    last = list(start)
    gross = [0] * len(motors)

    while time.ticks_diff(time.ticks_ms(), t0) < MEASURE_MS:
        time.sleep_ms(SAMPLE_MS)
        for i, m in enumerate(motors):
            now = read_count(m.sm)
            gross[i] += abs(now - last[i])
            last[i] = now

    elapsed = time.ticks_diff(time.ticks_ms(), t0)
    out = []
    for i in range(len(motors)):
        net_rate = (last[i] - start[i]) * 1000.0 / elapsed
        gross_rate = gross[i] * 1000.0 / elapsed
        coh = (abs(net_rate) / gross_rate * 100.0) if gross_rate else 100.0
        out.append((net_rate, gross_rate, coh))
    return out


def ramp_single(m, forward):
    m.direction(forward)
    print()
    print("%s  direction %s" % (m.name, "A" if forward else "B"))
    print("  duty     net/s   counts/s   coherence")
    print("  " + "-" * 38)

    for duty in STEPS:
        m.duty(duty)
        time.sleep_ms(SETTLE_MS)
        (net, gross, coh), = measure([m])
        print("  %3d%%  %+8.1f   %8.1f      %5.1f%%" % (duty, net, gross, coh))

    m.coast()
    time.sleep_ms(1500)


def ramp_pair(m1, m2, label, fwd1, fwd2):
    m1.direction(fwd1)
    m2.direction(fwd2)
    print()
    print(label)
    print("  duty      M1 net/s    M2 net/s     diff    M1 coh  M2 coh")
    print("  " + "-" * 58)

    for duty in STEPS:
        m1.duty(duty)
        m2.duty(duty)
        time.sleep_ms(SETTLE_MS)
        (n1, _, c1), (n2, _, c2) = measure([m1, m2])

        # compare magnitudes; directions may differ deliberately
        a1, a2 = abs(n1), abs(n2)
        if max(a1, a2) > 0:
            diff = (a1 - a2) / max(a1, a2) * 100.0
            diff_s = "%+6.1f%%" % diff
        else:
            diff_s = "     --"

        print("  %3d%%  %+10.1f  %+10.1f   %s   %5.1f%%  %5.1f%%"
              % (duty, n1, n2, diff_s, c1, c2))

    m1.coast()
    m2.coast()
    time.sleep_ms(1500)


def main():
    stby = Pin(PIN_STBY, Pin.OUT, value=0)

    m1 = Motor("Motor 1", 2, 3, 4, 10, 11, 0)
    m2 = Motor("Motor 2", 5, 6, 7, 12, 13, 1)

    print("Dual motor test - PWM %d Hz, STBY on GP%d" % (PWM_HZ, PIN_STBY))

    try:
        stby.value(1)

        # 1. Motor 2 on its own, both ways
        ramp_single(m2, True)
        ramp_single(m2, False)

        # 2. matched duty, same direction - the speed-matching check
        ramp_pair(m1, m2, "BOTH, same direction", True, True)

        # 3. opposed - confirms the channels are independent
        ramp_pair(m1, m2, "BOTH, opposed directions", True, False)

        print()
        print("diff is (M1 - M2) as a percentage of the faster one.")
        print("Large diff at low duty is usually stiction, not a wiring fault -")
        print("Motor 1 already showed a 12% direction asymmetry at 20% duty.")
        print("A diff that persists at 100% means genuinely mismatched motors,")
        print("which the crawler's control loop will have to trim out.")

    finally:
        m1.shutdown()
        m2.shutdown()
        stby.value(0)
        print()
        print("stopped - both motors coasting, driver disabled")


main()
