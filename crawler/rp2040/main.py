"""
Pipecrawler - RP2040 <-> Radxa UART link  (MicroPython, RP2040-Zero)

Runs at boot.  Decodes both encoders on PIO, streams their counts to the Radxa
over UART0, and drives both treads on command.

Everything on the wire is LEFT / RIGHT, and positive always means forward - for
both duty and encoder counts.  The mapping from tread to driver channel, motor
direction and encoder pins lives in LEFT / RIGHT below, measured 2026-10-14:

    Left tread  = TB6612 channel B (PWM GP5, IN GP6/GP7), encoder on GP10/GP11
    Right tread = TB6612 channel A (PWM GP2, IN GP3/GP4), encoder on GP12/GP13
    The treads are mirrored, so the right motor is driven reversed.

Wiring:
    GP0 (UART0 TX) -> Radxa pin 16 / UART4_RX_M1
    GP1 (UART0 RX) <- Radxa pin 18 / UART4_TX_M1
    GND            -- shared with Radxa
    STBY GP8 (shared)

Protocol, 115200 8N1, one ASCII line per message, '\\n' terminated:
    RP2040 -> Radxa   E <ms> <left> <right> <duty_l> <duty_r>    every STREAM_MS
                      PONG                        reply to PING
                      OK ZERO                     reply to ZERO
                      WDOG                        watchdog stopped the motors
                      READY                       once at boot
                      ERR <text>                  bad command
    Radxa -> RP2040   PING                        link check (also feeds watchdog)
                      ZERO                        reset both counts to 0
                      M <left> <right>            -100..100, positive = forward
                      STOP                        coast both, driver to standby

Watchdog: while either motor is running, the Radxa must send a command at least
every WATCHDOG_MS.  If it goes quiet (script crashed, cable pulled), both motors
stop and STBY drops.  Send M at ~10 Hz to keep driving.

Upload (RP2040 on USB, Radxa 5V wire unplugged), from the repo root:
    python -m mpremote connect COM3 cp crawler/rp2040/main.py :main.py
Self-contained: the PIO decoder is copied from tests/rp2040/encoder_test.py.
"""

import time

import rp2
from machine import PWM, UART, Pin

UART_ID = 0
BAUD = 115200
PIN_TX = 0
PIN_RX = 1
PIN_STBY = 8
PWM_HZ = 20_000
STREAM_MS = 50          # 20 Hz
WATCHDOG_MS = 500
MAX_DUTY = 100          # lower this to cap speed during testing

# (pwm, in1, in2, enc_a, enc_b, dir_sign, enc_sign)
#   dir_sign: -1 if positive duty drives this tread backward
#   enc_sign: -1 if driving forward makes the raw count go down
LEFT = (5, 6, 7, 10, 11, +1, -1)
RIGHT = (2, 3, 4, 12, 13, -1, +1)

# PIO clock.  >=6 PIO cycles per quadrature state, so 2 MHz gives ~60x headroom
# over a 12 V N20.  Lower it for more noise rejection.
PIO_FREQ = 2_000_000


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



class Motor:
    def __init__(self, pin_pwm, pin_in1, pin_in2, enc_a, enc_b,
                 dir_sign, enc_sign, sm_id):
        self.dir_sign = dir_sign
        self.enc_sign = enc_sign
        self.in1 = Pin(pin_in1, Pin.OUT, value=0)
        self.in2 = Pin(pin_in2, Pin.OUT, value=0)
        self.pwm = PWM(Pin(pin_pwm))
        self.pwm.freq(PWM_HZ)
        self.pwm.duty_u16(0)
        self.duty = 0

        a = Pin(enc_a, Pin.IN, Pin.PULL_UP)
        b = Pin(enc_b, Pin.IN, Pin.PULL_UP)
        self.sm = rp2.StateMachine(sm_id, quadrature_2x, freq=PIO_FREQ,
                                   in_base=b, jmp_pin=a)
        self.sm.exec("set(x, 0)")
        self.sm.active(1)
        self.zero = read_count(self.sm)

    def set(self, pct):
        pct = max(-MAX_DUTY, min(MAX_DUTY, pct))
        self.duty = pct
        if pct == 0:
            self.coast()
            return
        fwd = (pct > 0) == (self.dir_sign > 0)
        self.in1.value(1 if fwd else 0)
        self.in2.value(0 if fwd else 1)
        self.pwm.duty_u16(int(65535 * abs(pct) / 100))

    def coast(self):
        self.duty = 0
        self.pwm.duty_u16(0)
        self.in1.value(0)
        self.in2.value(0)

    def count(self):
        return self.enc_sign * (read_count(self.sm) - self.zero)

    def rezero(self):
        self.zero = read_count(self.sm)


def main():
    # Driver disabled until the first M command.
    stby = Pin(PIN_STBY, Pin.OUT, value=0)
    motors = (Motor(*LEFT, sm_id=0), Motor(*RIGHT, sm_id=1))

    def stop():
        for m in motors:
            m.coast()
        stby.value(0)

    uart = UART(UART_ID, baudrate=BAUD, tx=Pin(PIN_TX), rx=Pin(PIN_RX))
    uart.write(b"READY\n")
    print("uart link up: UART%d %d baud, TX=GP%d RX=GP%d"
          % (UART_ID, BAUD, PIN_TX, PIN_RX))

    rx = b""
    t_next = time.ticks_ms()
    t_heard = time.ticks_ms()
    while True:
        # -- commands from the Radxa --
        n = uart.any()
        if n:
            rx += uart.read(n)
            while b"\n" in rx:
                line, rx = rx.split(b"\n", 1)
                parts = line.strip().upper().split()
                if not parts:
                    continue
                cmd = parts[0]
                t_heard = time.ticks_ms()
                if cmd == b"PING":
                    uart.write(b"PONG\n")
                elif cmd == b"ZERO":
                    for m in motors:
                        m.rezero()
                    uart.write(b"OK ZERO\n")
                elif cmd == b"STOP":
                    stop()
                elif cmd == b"M" and len(parts) == 3:
                    try:
                        d1, d2 = int(parts[1]), int(parts[2])
                    except ValueError:
                        uart.write(b"ERR bad duty\n")
                        continue
                    motors[0].set(d1)       # left
                    motors[1].set(d2)       # right
                    stby.value(1 if (d1 or d2) else 0)
                else:
                    uart.write(b"ERR unknown " + line.strip()[:20] + b"\n")
            if len(rx) > 64:            # garbage with no newline - drop it
                rx = b""

        now = time.ticks_ms()

        # -- watchdog --
        if stby.value() and time.ticks_diff(now, t_heard) > WATCHDOG_MS:
            stop()
            uart.write(b"WDOG\n")

        # -- stream counts --
        if time.ticks_diff(now, t_next) >= 0:
            t_next = time.ticks_add(t_next, STREAM_MS)
            uart.write(b"E %d %d %d %d %d\n" % (
                now, motors[0].count(), motors[1].count(),
                motors[0].duty, motors[1].duty))

        time.sleep_ms(2)


main()
