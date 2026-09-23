# Encoder bring-up log — Motor 1

**Date:** 2026-09-21
**Board:** Waveshare RP2040-Zero, MicroPython v1.29.0 (2026-08-24), COM6
**Motor:** N20 worm-gear motor with quadrature encoder (Motor 1 of 2)
**Driver:** none — TB6612FNG not yet received

Validates the encoder signal path end to end without a motor driver. The TB6612
only sits between the RP2040 and the motor *windings*; the encoder is a separate
4-wire logic interface, and the N20's 6-pin connector keeps the two electrically
independent (pins 1/6 = windings, pins 2–5 = encoder PCB). So this work did not
need to wait on the driver.

## Configuration under test

| Signal | Motor pin | RP2040-Zero |
|---|---|---|
| Encoder A | 3 / C1_EncoderA | GP10 |
| Encoder B | 4 / C2_EncoderB | GP11 |
| Encoder Vcc | 5 / Vcc_Encoder+ | 3V3 pad |
| Encoder GND | 2 / GND_Encoder- | GND |
| Motor + | 6 / M2_MotorPSU+ | bench PSU + |
| Motor − | 1 / M1_MotorPSU- | bench PSU − |

Board powered from USB-C. PoE HAT and the 5V rail not involved. Bench PSU
current limit 0.5 A. **No decoupling capacitors fitted** — see open items.

## Confirmed

**Encoder runs at 3.3V.** This closes the `VERIFY encoder voltage` item on the
pinout sheet. Probing each line once with a pull-up and once with a pull-down,
both ignored the pull — they are actively driven, meaning powered push-pull hall
outputs. The 5V-plus-divider fallback is not needed. GPIO is not 5V tolerant, so
3.3V is also the preferable answer.

**PIO decoder is correct.** Verified twice: simulated against a synthetic
quadrature waveform (forward, reverse, direction changes, signed wrap through
zero), then run on hardware. Decode holds down to 6 PIO cycles per quadrature
state — at the 2 MHz state machine clock that is ~333k states/s, against ~3.8k
observed at 12V. Roughly 90× headroom.

**Zero count loss under power, across the full voltage range.**

| Supply | counts/s (steady) | Total counts | Coherence |
|---|---|---|---|
| 3V | 862 | 13,739 | 100.0% |
| 6V | 1,823 | 35,571 | 100.0% |
| 12V | 3,780 | 28,700 | 100.0% |

Coherence is `|net| / gross`, where gross counts every reversal. In all three
runs `net/s` and `counts/s` were *identical* in every one-second window — not
rounded to 100%, but literally zero reversals recorded. Count was dead stable
before and after each run, and stayed clean through spin-down.

**Speed scales correctly with supply voltage:** 2.11× from 3V→6V and 2.07× from
6V→12V. The slight super-linearity is expected for a brushed DC motor, where
speed tracks (V − I·R) and the I·R drop shrinks proportionally as V rises. A
12V figure of 3,780 was predicted from the 6V data before measuring; actual was
3,780. Electrical noise would not scale this way, so this is independent
evidence the counts are genuine.

**Steady-state regulation** at 6V was ±0.1% at 1 Hz sampling (1822.6 … 1826.0),
so the encoder gives a low-noise velocity estimate to close a loop around.

**Direction** reads negative with the lead polarity in the table above.

## Inferred, not yet measured

**~20 counts per motor revolution (10 PPR per channel).** Hand-turning the rear
disc gave 19–20 counts per revolution, and that figure is the only one
consistent with the powered data:

| Supply | counts/s | motor RPM at 20 counts/rev |
|---|---|---|
| 3V | 862 | 2,590 |
| 6V | 1,823 | 5,470 |
| 12V | 3,780 | 11,340 |

All three are normal N20 speeds and scale correctly. For contrast, 14 counts/rev
would imply 16,200 RPM at 12V, and the 2 counts/rev suggested by an early
10-turn trial would imply 113,400 RPM — both impossible, which is what
identified those trials as hand-slip rather than measurement.

Counts per revolution must be even, since this decoder counts both edges of A
(counts = 2 × PPR).

## Driver bring-up — 2026-09-23

TB6612FNG fitted, Motor 1 driven through it at 20 kHz PWM. **No decoupling
capacitors fitted for these runs.**

| Duty | Direction A (counts/s) | Direction B (counts/s) | Coherence |
|---|---|---|---|
| 20% | +614.7 | −688.0 | 100% |
| 40% | +1448.2 | −1460.6 | 100% |
| 60% | +2225.2 | −2235.7 | 100% |
| 80% | +3008.0 | −3010.0 | 100% |
| 100% | +3778.9 | −3770.8 | 100% |

**PWM noise does not reach the encoder.** Zero reversals at all ten operating
points, with the bridge chopping current and no capacitors fitted. This was the
open question from the 2026-09-21 DC-only results.

**Driver loss is negligible.** 100% duty gives 3778.9 counts/s against 3780 for
the motor wired straight to the PSU at 12 V — a 0.03% difference, expected at
~50–100 mA, far below the 1 A at which the TB6612's saturation voltage is
specified.

**Direction signs are opposite**, confirming AIN1/AIN2 are correct.

### Low-speed asymmetry

Step sizes between duty points:

| Step | Direction A | Direction B |
|---|---|---|
| 20→40% | **+833.5** | +772.6 |
| 40→60% | +777.0 | +775.1 |
| 60→80% | +782.8 | +774.3 |
| 80→100% | +770.9 | +760.8 |

Direction B is linear throughout. Direction A is not: 20% duty yields 614.7
against B's 688.0, a 12% shortfall that has disappeared by 40%. This is
stiction, and worm gearboxes commonly show direction-dependent friction.

Consequence for control: an open-loop duty-to-speed table calibrated in one
direction will undershoot in the other at low speed. Prefer a closed velocity
loop. The dead zone below 20% duty has not been mapped.

## Both motors — 2026-09-23

Motor 2 wired to channel B (BIN1 GP6, BIN2 GP7, PWMB GP5, encoder GP12/GP13).
STBY shared. Both encoders decoded by their own PIO state machine, sharing one
copy of the program in instruction memory.

**Coherence was 100% in every row of every pass** — both motors, both
directions, matched and opposed, 10% to 100% duty. Motor 2's encoder on
GP12/GP13 is as clean as Motor 1's, and running two state machines concurrently
causes no interference.

### Speed matching

`diff` is (M1 − M2) as a percentage of the faster.

| Duty | Same direction | Opposed |
|---|---|---|
| 10% | −1.3% | +0.7% |
| 20% | −0.5% | +0.7% |
| 40% | +0.3% | +1.3% |
| 60% | +0.7% | +1.0% |
| 80% | +0.8% | +1.3% |
| 100% | +0.9% | +1.6% |

Under 2% across the whole range. Motor 2 is consistently marginally slower at
high duty, and the gap is slightly wider opposed than aligned, suggesting mild
direction-dependent friction in M2.

Opposed directions produce opposite signs, confirming BIN1/BIN2 polarity and
independent channel control.

### Cold stiction — important for control design

Motor 2's first-ever movement, standalone direction A, read **0.0 counts/s at
both 10% and 20% duty**. The same motor, same direction, same duty, in the
later paired pass read +304.2 and +690.3.

The difference is thermal and mechanical state: the standalone A pass ran from
cold and fully at rest, while by the paired pass the motor had already been to
100% duty. Breakaway torque from cold exceeds what 20% duty delivers, but 10% is
enough to sustain motion once moving.

Not yet confirmed — the test is to let it sit several minutes and re-run the
standalone pass. Zeros from cold and motion when warm confirms stiction.

**Consequence:** open-loop duty commands will not start reliably. Use a
kick-start pulse above breakaway, or integral action in the velocity loop that
winds up until the motor breaks free. A crawler that stalls on start-up deep in
a pipe is an expensive way to rediscover this.

## Open items

- **Confirm counts per motor revolution** with clean single-turn trials
  (`cpr_test.py`, `TURNS_PER_TRIAL = 1`). Expect 20.
- **Counts per *output* revolution** — the number that matters for odometry,
  since it converts counts into distance down the pipe. Measure under power:
  run at 3V, time N output revolutions, then
  `counts_per_output_rev = 862 × seconds ÷ N`. Dividing by 20 also yields the
  true gearbox ratio, worth checking against the listing.
- **UART to the Radxa** — untested.

## Not covered by these results

The 100% coherence figures were obtained with **steady DC from a bench supply**.
The TB6612 will chop motor current at PWM frequency with fast switching edges —
a substantially harsher environment than brush noise on a DC rail, and a
different mechanism (high dV/dt rather than commutation transients). The 50ft
tether and unshielded encoder runs in the final harness are different again.

These results show the encoder, the wiring and the decoder are sound. They do
**not** show the 0.1 µF capacitors across the motor terminals are unnecessary,
because the noise source motivating them is not yet in the circuit. Fit them.

## Tooling

| File | Purpose |
|---|---|
| `encoder_test.py` | PIO decoder + 1 Hz report (count, rates, coherence). Powered testing. |
| `hand_test.py` | Live per-change readout. Hand-turning, no motor power. |
| `cpr_test.py` | Hands-free counts-per-revolution trials. |

See [README.md](README.md) for wiring, flashing and the bench procedure.

Note on hand-turning: `cpr_test.py` measures **net** displacement, so slip or
back-and-forth cancels out and undercounts. The rear disc is small and stiff;
one deliberate revolution is worth more than ten hurried ones.
