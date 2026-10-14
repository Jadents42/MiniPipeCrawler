"""
Pipecrawler - Motor 1 encoder bring-up test  (MicroPython, RP2040-Zero)

Reads the N20 quadrature encoder using a PIO state machine so no counts are
lost at speed.  Python only polls a counter that the PIO maintains.

Wiring (per Pipecrawler Pinout Sheet, Motor 1):
    Motor pin 3 / C1_EncoderA  ->  GP10
    Motor pin 4 / C2_EncoderB  ->  GP11
    Motor pin 5 / Vcc_Encoder+ ->  3V3 pad      (NOT 5V - GPIO is not 5V tolerant)
    Motor pin 2 / GND_Encoder- ->  GND
    Motor pins 1 and 6 are the windings -> bench PSU, nothing to do with this test.

Run it, spin the motor, watch the numbers.  See README.md for the procedure.
"""

import time

import rp2
from machine import Pin

# ---------------------------------------------------------------- config ----

PIN_A = 10          # C1_EncoderA
PIN_B = 11          # C2_EncoderB

# PIO clock.  Two things depend on it:
#
#   Ceiling.  The decode path needs >=6 PIO cycles per quadrature state (verified
#   by simulating the program against a synthetic waveform).  At 2 MHz that is
#   3 us per state, or ~333k states/s.  A 12 V N20 tops out near 6k states/s, so
#   there is roughly 60x of headroom.
#
#   Noise rejection.  The polling loop samples every 4 cycles (2 us here), so a
#   glitch much narrower than that will usually fall between samples and be
#   missed.  That is statistical, not a real filter - it reduces sensitivity to
#   brush noise, it does not replace the 0.1uF caps across the motor terminals.
#
# Lower this for more noise rejection, raise it only if you genuinely outrun it.
PIO_FREQ = 2_000_000

# Fill this in once you have measured it (see README).  0 = unknown, skip RPM.
COUNTS_PER_OUTPUT_REV = 0

SAMPLE_MS = 10      # how often to poll the counter
REPORT_MS = 1000    # how often to print a line


# ------------------------------------------------------------- pio decode ----
#
# 2x quadrature: counts both edges of A, using the level of B to pick direction.
#     A rising  + B low   -> forward        A rising  + B high  -> reverse
#     A falling + B high  -> forward        A falling + B low   -> reverse
#
# X holds the signed count.  Y is scratch for reading B.  The two polling loops
# publish X to the RX FIFO continuously, which is what lets read_count() below
# guarantee a fresh (non-stale) sample.
#
# jmp_pin is A, in_base is B - the two are independent, which is the trick that
# leaves X free to be the counter.

@rp2.asm_pio(in_shiftdir=rp2.PIO.SHIFT_LEFT)
def quadrature_2x():
    # ---- A is low: publish, and poll for the rising edge ----
    label("wait_rise")
    mov(isr, x)
    push(noblock)
    jmp(pin, "rose")
    jmp("wait_rise")

    label("rose")
    mov(isr, null)
    in_(pins, 1)                    # ISR = B
    mov(y, isr)
    jmp(not_y, "rise_fwd")          # B == 0 -> forward
    jmp(x_dec, "wait_fall")         # B == 1 -> reverse (x_dec always decrements)
    jmp("wait_fall")

    label("rise_fwd")               # increment: ~(~x - 1) == x + 1
    mov(x, invert(x))
    jmp(x_dec, "rf_done")
    label("rf_done")
    mov(x, invert(x))

    # ---- A is high: publish, and poll for the falling edge ----
    label("wait_fall")
    mov(isr, x)
    push(noblock)
    jmp(pin, "wait_fall")

    mov(isr, null)
    in_(pins, 1)                    # ISR = B
    mov(y, isr)
    jmp(not_y, "fall_rev")          # B == 0 -> reverse
    mov(x, invert(x))               # B == 1 -> forward
    jmp(x_dec, "ff_done")
    label("ff_done")
    mov(x, invert(x))
    jmp("wait_rise")

    label("fall_rev")
    jmp(x_dec, "fr_done")
    label("fr_done")
    jmp("wait_rise")


# ------------------------------------------------------------------ plumbing --

def read_count(sm, timeout_ms=200):
    """Drain the FIFO, then take one more sample.

    The drained entries may be arbitrarily old; the one read after the drain was
    pushed by the polling loop after we emptied it, so it is current.
    """
    for _ in range(sm.rx_fifo()):
        sm.get()

    t0 = time.ticks_ms()
    while not sm.rx_fifo():
        if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
            raise RuntimeError(
                "PIO is not publishing - state machine stalled or not active")

    v = sm.get()
    return v - 0x100000000 if v & 0x80000000 else v     # to signed


def static_check(pin_a, pin_b, ms=300):
    """Sample the idle pin levels before anything spins.

    Both pins stuck at 1 with nothing turning is the expected resting state
    (internal pull-ups).  Both stuck at 0 usually means Vcc is missing or the
    A/B lines are swapped onto GND.
    """
    seen_a, seen_b = set(), set()
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < ms:
        seen_a.add(pin_a.value())
        seen_b.add(pin_b.value())
    return seen_a, seen_b


def main():
    # Pull-ups matter: plenty of N20 encoder boards use open-collector hall
    # outputs, which read as nothing at all without them.
    pin_a = Pin(PIN_A, Pin.IN, Pin.PULL_UP)
    pin_b = Pin(PIN_B, Pin.IN, Pin.PULL_UP)

    print("Pipecrawler encoder test - A=GP%d  B=GP%d  filter=%.1fus"
          % (PIN_A, PIN_B, 4e6 / PIO_FREQ))

    seen_a, seen_b = static_check(pin_a, pin_b)
    print("idle levels: A=%s  B=%s" % (sorted(seen_a), sorted(seen_b)))
    if seen_a == {0} and seen_b == {0}:
        print("  !! both lines low - check encoder Vcc (3V3) and GND first")
    print()

    sm = rp2.StateMachine(0, quadrature_2x, freq=PIO_FREQ,
                          in_base=pin_b, jmp_pin=pin_a)
    sm.exec("set(x, 0)")
    sm.active(1)

    zero = read_count(sm)       # whatever the startup edge did, call it zero
    last = zero
    window_start = zero
    gross = 0                   # sum of |delta| - counts every reversal
    t_report = time.ticks_ms()

    print("  count     net/s   counts/s   coherence" +
          ("      rpm" if COUNTS_PER_OUTPUT_REV else ""))
    print("  " + "-" * (44 if COUNTS_PER_OUTPUT_REV else 35))

    while True:
        time.sleep_ms(SAMPLE_MS)

        now_count = read_count(sm)
        gross += abs(now_count - last)
        last = now_count

        elapsed = time.ticks_diff(time.ticks_ms(), t_report)
        if elapsed < REPORT_MS:
            continue

        net = now_count - window_start
        net_rate = net * 1000.0 / elapsed
        gross_rate = gross * 1000.0 / elapsed

        # Coherence: how much of the movement was net travel rather than
        # back-and-forth.  Steady rotation sits at ~100%.  A low number with a
        # high counts/s is electrical noise, not a bug in this code.
        coherence = (abs(net) / gross * 100.0) if gross else 100.0

        line = "%+8d  %+8.1f   %8.1f      %5.1f%%" % (
            now_count - zero, net_rate, gross_rate, coherence)
        if COUNTS_PER_OUTPUT_REV:
            line += "  %+7.1f" % (net_rate / COUNTS_PER_OUTPUT_REV * 60.0)
        print(line)

        gross = 0
        window_start = now_count
        t_report = time.ticks_ms()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped")
