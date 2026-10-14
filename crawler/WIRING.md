# As-built wiring

The crawler as wired and verified on 2026-10-14: both treads driving through the
TB6612, both encoders counting, Radxa ↔ RP2040 UART, live camera. Firmware that
matches this wiring is [rp2040/main.py](rp2040/main.py).

**Wire every RP2040 connection by the GP label on the silkscreen**, and every
TB6612 connection by its printed label (VM, VCC, PWMA…). Pin *numbers* from the
Pinout Sheet or product pictures use different schemes and have already put
wires in the wrong hole — see [the lessons below](#lessons-that-cost-a-debugging-session).

## System at a glance

```
Bench PSU 12V ──► 12V rail ──► TB6612 VM ──► left + right motors
Radxa pin 4 (5V) ─► 5V rail ──► RP2040 5V
RP2040 3V3 ───────► 3.3V rail ─► TB6612 VCC, left encoder +, right encoder +
                    GND rail ◄── everything (one shared ground)

Radxa UART4 ◄──► RP2040 UART0          Radxa CSI ◄── IMX219 camera ribbon
```

## Rail board

Small perfboard with four rails plus a spare: **GND, 3.3V, 5V, 12V**. One GND
rail serves as the common ground for the whole robot.

| Rail | Fed by | Feeds |
|---|---|---|
| 12V | Bench PSU + (12V, 0.5 A OCP; no buck yet) | TB6612 VM |
| 5V | Radxa pin 4 (**orange**) | RP2040 5V |
| 3.3V | RP2040 3V3 pad | TB6612 VCC (blue), both encoder + (harness **black**) |
| GND | Bench PSU −, Radxa pin 6 | RP2040 GND, TB6612 GND, both encoder GND (harness **blue**) |

Before powering a freshly soldered board, beep-test every rail against every
other rail — 12V to anything, and 3.3V to GND, must read open.

### USB in = orange wire out

The RP2040-Zero's 5V pad connects straight to its USB VBUS. With the orange wire
in, plugging the RP2040 into a PC **back-feeds the PC's USB into the Radxa** and
boots it (seen 2026-10-13). Pull the orange wire whenever the RP2040 is on USB;
leave GND connected. Having the Radxa powered while the orange wire is out is
fine. A Schottky diode (1N5817/1N5819, stripe toward the rail) in the orange
wire would remove the need to pull it.

## Radxa ↔ RP2040

| Net | Radxa pin | RP2040 | Colour | Note |
|---|---|---|---|---|
| UART TX | 18 / UART4_TX_M1 | GP1 (UART0 RX) | Green | 115200 8N1 |
| UART RX | 16 / UART4_RX_M1 | GP0 (UART0 TX) | Yellow | |
| +5V | 4 | 5V rail → RP2040 5V | Orange | see back-feed rule above |
| GND | 6 | GND rail | Black | |

Radxa side: UART4-M1 overlay enabled in `rsetup`, appears as `/dev/ttyS4`; user
must be in the `dialout` group. Pins 8 and 10 are the debug console — do not use.

## TB6612 driver

| TB6612 label | Connects to | Colour | Note |
|---|---|---|---|
| VM | 12V rail | Red | motor supply, 13.5 V max |
| VCC | 3.3V rail | Blue | **logic** supply, 6 V abs max — never 12V |
| GND | GND rail | Black | the module ties its GND pins together; check with a meter |
| STBY | GP8 | White | high = enabled; shared by both channels |
| PWMA / AIN1 / AIN2 | GP2 / GP3 / GP4 | Purple / Grey / Brown | channel A = **right** tread |
| PWMB / BIN1 / BIN2 | GP5 / GP6 / GP7 | Purple / Grey / Brown | channel B = **left** tread |
| AO1 / AO2 | right motor harness pin 6 / pin 1 | Red / White | |
| BO1 / BO2 | left motor harness pin 6 / pin 1 | Red / White | |

**VM and VCC are different rails.** VCC also sets the input thresholds
(VIH = 0.7 × VCC), so it runs at 3.3 V to match the RP2040's logic level; at 5 V
the RP2040's highs would sit below the guaranteed threshold. 12 V on VCC destroys
the chip.

## Motors and encoders

### Harness colours

Counting pins as the Pinout Sheet does, from the white end:

| Pin | Wire | Function |
|---|---|---|
| 1 | White | Motor − |
| 2 | **Blue** | Encoder GND |
| 3 | Green | Encoder C1 |
| 4 | Yellow | Encoder C2 |
| 5 | **Black** | Encoder + (3.3V) |
| 6 | Red | Motor + |

**The encoder power colours are backwards from the usual convention:** harness
black goes to 3.3V, harness blue goes to GND. The product picture numbers the
connector from the red end, so its pin 1 is our pin 6 — its labels agree once
you account for that.

### As wired

| Tread | Driver channel | Encoder yellow | Encoder green | Firmware |
|---|---|---|---|---|
| Left | B | GP10 | GP11 | `LEFT = (5, 6, 7, 10, 11, +1, -1)` |
| Right | A | GP12 | GP13 | `RIGHT = (2, 3, 4, 12, 13, -1, +1)` |

Both encoders are wired the same way round (yellow on the lower GP). Which
channel is "A" only sets the count direction, and the firmware's sign flags
handle that. The treads are mirrored, so the right motor is driven reversed in
firmware; on the wire, `M 50 50` means both treads forward and both counts go
positive. If anything is rewired, update the `LEFT` / `RIGHT` lines in
[main.py](rp2040/main.py) instead of re-soldering.

Encoders run at **3.3 V only**: RP2040 GPIO is not 5 V tolerant, and the N20
encoders are push-pull outputs that work fine at 3.3 V (verified 2026-09-21,
~78,000 counts at 100% coherence — [BRINGUP.md](../tests/rp2040/BRINGUP.md)).

## Camera

Arducam IMX219 on the Radxa's CSI connector; the ribbon supplies its power. Shows
up as `/dev/video-camera0`, native rate is not exactly 30 fps, so don't force
`framerate=30/1` in GStreamer caps.

## Lessons that cost a debugging session

- **Sheet numbers vs GP labels (2026-09-23).** The Pinout Sheet numbers RP2040
  pins as GP + 1. Wiring from those numbers put every control line one pad high;
  STBY landed on GP9, the driver stayed in standby, and nothing moved with no
  obvious fault. Ignore the number before the slash; use the GP label.
- **TB6612 numbering.** The sheet uses SparkFun numbering (VM = 9, VCC = 10); the
  red module's picture counts differently (VM = 1, VCC = 2). Mixing them can put
  12 V on GND. Use the printed labels.
- **Encoder looks dead, reads exactly 0 (2026-10-14).** One floating signal wire
  makes the 2x decoder add and subtract on alternate edges, netting zero even
  though the motor and sensor are fine. The right encoder's green wire was
  unseated; reseating the connector fixed it. Test each pin with pull-up vs
  pull-down: a pin that follows the pull is connected to nothing.
- **Low duty doesn't move the treads.** Under ~30–40% the N20s can't overcome the
  TPU treads' load and stiction; they buzz instead of turning. Don't leave them
  stalled at high duty.

## Limits

- TB6612 **VM 13.5 V** operating (15 V abs), **VCC 6 V** abs, ~1.2 A continuous per channel.
- **STBY low = nothing moves** — first thing to check when the driver "is dead".
- The future 28 V tether supply must only ever reach a buck input, never a rail.

Datasheet: <https://www.waveshare.com/w/upload/6/62/TB6612FNG_datasheet_en.pdf>
