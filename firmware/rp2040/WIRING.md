# As-built wiring — Motor 1 + TB6612

Corrected against the TB6612FNG datasheet and the 2026-09-21 encoder bring-up.
**Two rows here deviate from the Pipecrawler Pinout Sheet**; both are marked
CORRECTED below, and the sheet should be updated to match.

## RP2040-Zero pin numbering

The Pinout Sheet numbers RP2040 pins as **pin = GP number + 1** (GP0–GP29 are
pins 1–30), which is the SnapEDA schematic symbol order. It is self-consistent —
verified across all 14 GPIO rows — but those numbers are *not* printed on the
board. The silkscreen shows `GP2`, `GP10` and so on, so wire by the GP label and
use the sheet number only for cross-referencing.

Both columns are given below.

### This has already cost one debugging session

On 2026-09-23 all four control lines were wired from the sheet's *numbers*
rather than its GP labels, putting every one of them a pad too high. STBY landed
on GP9, which nothing drives, so the TB6612 stayed in standby: zero PSU current,
zero encoder counts, and no obvious fault anywhere. The probe on the driver's
STBY pin read mostly `low` with occasional `HIGH`/`UNSTABLE` — the signature of
a *floating* input against a pull-down, not of a broken wire.

| Signal | Sheet says | Pad to use |
|---|---|---|
| PWM_A | `3 / GP2` | **2** |
| AIN1 | `4 / GP3` | **3** |
| AIN2 | `5 / GP4` | **4** |
| STBY | `9 / GP8` | **8** |

**The rule for every row in the sheet: ignore the number before the slash, use
the GP label after it.** The encoder rows were wired by GP label from the start,
which is why that half of the system worked perfectly throughout.

## TB6612 board layout

The sheet's TB6612 numbering follows the SparkFun-style breakout, 1–8 down one
side and 9–16 down the other:

```
   1     2     3     4     5     6     7     8
 PWMA  AIN2  AIN1  STBY  BIN1  BIN2  PWMB  GND

   9    10    11    12    13    14    15    16
  VM   VCC   GND   A01   A02   B02   B01   GND
```

### VM and VCC are two different rails — do not merge them

| Pin | Label | Purpose | Voltage | Absolute max |
|---|---|---|---|---|
| 9 | `VM` | Motor supply, drives the windings | **12 V** | 15 V |
| 10 | `VCC` | Logic supply; also sets the input thresholds | **3.3 V** | **6 V** |

`VCC` reads like the main supply but is the small-signal one — the datasheet
pin list calls it "Small signal supply" and rates it to 6 V absolute, against
15 V for VM. **12 V on pin 10 destroys the chip.** Both rails must be present:
VM alone leaves the logic unpowered, VCC alone leaves the outputs dead.

## Control — RP2040-Zero to TB6612

| Net | GPIO | Sheet pin | TB6612 pin | Gauge | Colour | Note |
|---|---|---|---|---|---|---|
| PWM_A | GP2 | 3 | 1 / PWMA | 26 | White | Motor 1 speed |
| AIN2 | GP4 | 5 | 2 / AIN2 | 26 | Purple | Motor 1 direction |
| AIN1 | GP3 | 4 | 3 / AIN1 | 26 | Grey | Motor 1 direction |
| STBY | GP8 | 9 | 4 / STBY | 26 | Orange | High = enabled; low = nothing moves |

## Power

| Net | From | To | Gauge | Colour | Note |
|---|---|---|---|---|---|
| +3V3 | RP2040 3V3 pad | TB6612 10 / VCC_Logic | 22 | Red | **CORRECTED — sheet says 5V rail** |
| +12V | Buck / bench PSU | TB6612 9 / VM_Driving | 18 | Red | 13.5 V operating max; 1000 µF bulk cap |
| GND | Star ground | TB6612 8, 11, 16 | 22 | Black | all three GND pins |
| GND | Star ground | RP2040-Zero GND | 22 | Black | shared reference |

## Motor outputs

| Net | TB6612 pin | Motor 1 pin | Gauge | Colour | Note |
|---|---|---|---|---|---|
| M1_POS | 12 / AO1 | 6 / M2_MotorPSU+ | 18 | Red | twist with M1_NEG |
| M1_NEG | 13 / AO2 | 1 / M1_MotorPSU- | 18 | Black | 0.1 µF cap across terminals |

## Encoder

| Net | Motor 1 pin | To | Gauge | Colour | Note |
|---|---|---|---|---|---|
| ENC1_A | 3 / C1_EncoderA | GP10 (sheet pin 11) | 26 | Blue | PIO base pin |
| ENC1_B | 4 / C2_EncoderB | GP11 (sheet pin 12) | 26 | Blue/white | must be base+1 |
| +3V3 | 5 / Vcc_Encoder+ | RP2040 3V3 pad | 26 | Red | **CORRECTED — sheet says 5V rail** |
| GND | 2 / GND_Encoder- | Star ground | 26 | Black | RP2040 GND is sheet pin 32 |

### The sheet has no 3V3 row

Its only RP2040 power entries are `32 / GND` and `33 / 5V`. Both corrections
above need a 3V3 rail, so a row has to be added. By the sheet's own pattern
GP0–GP29 take pins 1–30, leaving 31/32/33 for the three power pads; with GND at
32 and 5V at 33, **3V3 is most likely pin 31** — confirm against the SnapEDA
symbol before committing it, as it cannot be derived from the existing rows.

## Why both corrections are 3V3 and not 5V

**Encoder Vcc.** RP2040 GPIO is not 5V tolerant. Powering the encoder at 5V
makes its A/B outputs swing to 5V straight into GP10/GP11. The sheet's
`VERIFY encoder voltage` note was resolved on 2026-09-21: both channels are
powered push-pull outputs that work correctly at 3.3V, confirmed across ~78,000
counts at 100% coherence. See [BRINGUP.md](BRINGUP.md).

**TB6612 VCC_Logic.** The datasheet specifies the control-input threshold
*relative to VCC*, not as a fixed voltage:

```
Control input voltage   VIH   Vcc × 0.7  ―  Vcc + 0.2
                        VIL   -0.2       ―  Vcc × 0.3
```

| VCC_Logic | VIH minimum | RP2040 drives | Result |
|---|---|---|---|
| 5.0 V | 3.50 V | 3.3 V | below spec |
| 3.3 V | 2.31 V | 3.3 V | comfortable margin |

At 5V VCC the RP2040's logic highs sit under the guaranteed input-high
threshold. It may appear to work at room temperature, since typical thresholds
run below the guaranteed worst case, but the failure mode is intermittent —
stuttering, ignored direction changes, or drop-out as the electronics warm up
inside the pipe. VCC's operating range is 2.7–5.5 V, so 3.3 V is well within it.
`STBY` shares the same `Vcc × 0.7` threshold.

Datasheet: <https://www.waveshare.com/w/upload/6/62/TB6612FNG_datasheet_en.pdf>

## Motor 2 — channel B

Pad numbers below are already resolved from the sheet's GP labels. Use the
**Pad** column; the sheet's own numbers are one higher and will put every wire
in the wrong hole.

### Control

| Net | GPIO | **Pad** | Sheet says | TB6612 pin |
|---|---|---|---|---|
| BIN1 | GP6 | **6** | `7 / GP6` | 5 / BIN1 |
| BIN2 | GP7 | **7** | `8 / GP7` | 6 / BIN2 |
| PWM_B | GP5 | **5** | `6 / GP5` | 7 / PWMB |

**STBY is shared.** It already enables both channels — do not add a second one.

**BIN2 is the dangerous row.** The sheet calls it `8 / GP7`. Pad 8 is GP8, which
is STBY. Wiring BIN2 from the sheet number lands it on the working STBY line and
breaks Motor 1 as well as Motor 2.

### Outputs — note the reversed order

| Net | TB6612 pin | Motor 2 pin | Gauge | Colour |
|---|---|---|---|---|
| M2_POS | **15 / BO1** | 6 / M2_MotorPSU+ | 18 | Red |
| M2_NEG | **14 / BO2** | 1 / M1_MotorPSU- | 18 | Black |

Pins 12–15 run `A01, A02, B02, B01`. **B02 comes before B01**, so the positive
output is the *higher* pin number — the opposite of channel A. Twist the pair,
0.1 µF across the motor terminals.

### Encoder

| Net | Motor 2 pin | GPIO | **Pad** | Sheet says |
|---|---|---|---|---|
| ENC2_A | 3 / C1_EncoderA | GP12 | **12** | `13 / GP12` |
| ENC2_B | 4 / C2_EncoderB | GP13 | **13** | `14 / GP13` |
| +3V3 | 5 / Vcc_Encoder+ | 3V3 pad | — | **sheet says 5V — wrong** |
| GND | 2 / GND_Encoder- | star ground | — | |

The encoder pads happen to match their GP numbers here only by coincidence of
how the table reads — GP12 is pad 12, GP13 is pad 13. Still go by the GP label.

Encoder Vcc is 3V3 for the same reason as Motor 1: RP2040 GPIO is not 5V
tolerant.

## Limits worth remembering

- **VM operating max 13.5 V** (15 V absolute). Running at 12 V leaves 1.5 V of
  headroom — the 28 V tether rail must never reach this pin.
- **VCC absolute max 6 V**; control inputs rated −0.2 to 6 V.
- **All three TB6612 GND pins** (8, 11, 16) must be connected.
- **STBY high to enable.** The most common "driver is dead" cause.
