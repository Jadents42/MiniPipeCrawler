# Motor 1 encoder bring-up

Validates the N20 encoder against the RP2040-Zero with no motor driver in the
loop. The TB6612 only ever sits between the RP2040 and the motor *windings* —
the encoder is a separate 4-wire logic interface — so none of this has to wait
for the drivers to arrive.

Results from the 2026-09-21 run are in **[BRINGUP.md](BRINGUP.md)** — what was
confirmed, what is still inferred, and what these tests do not cover.

## Wiring

Per the Pipecrawler Pinout Sheet, Motor 1. The N20 6-pin connector splits into
two electrically independent halves: pins 1 and 6 are the windings, pins 2–5 are
the encoder PCB. That split is what makes this test possible.

| Motor pin | Goes to | Note |
|---|---|---|
| 3 / C1_EncoderA | GP10 | PIO base pin |
| 4 / C2_EncoderB | GP11 | must be base+1 |
| 5 / Vcc_Encoder+ | **3V3 pad** | not 5V — GPIO is not 5V tolerant |
| 2 / GND_Encoder- | GND | |
| 6 / M2_MotorPSU+ | bench PSU + | |
| 1 / M1_MotorPSU- | bench PSU − | |

Power the RP2040 from USB-C. The PoE HAT and the 5V rail are not involved.

### On encoder Vcc

The sheet flags `VERIFY encoder voltage` and it is still open. Most N20 hall
encoders accept 3–5V, so the 3V3 pad will probably work, and trying it is
zero-risk — under-powering a hall sensor doesn't damage it, it just may not
output. If you get no pulses at 3.3V, that means 5V + a 10k/20k divider on
*each* of A and B, not a dead board.

Never divide or buck a power rail for this. Dividers are for low-current signals
only, which is why the MQ-135 gets one on its analog output but full 5V on Vcc.

## Flashing

1. Grab the official Raspberry Pi Pico MicroPython `.uf2` from
   <https://micropython.org/download/RPI_PICO/>. It runs fine on the RP2040-Zero
   — the only board difference is the RGB LED on GP16, which this doesn't use.

   Verified against **v1.29.0** (2026-08-24, current stable). Every `rp2` API
   this uses — the `StateMachine` constructor kwargs, `exec`/`get`/`rx_fifo`/
   `active`, and each PIO instruction — is present and unchanged there. The PIO
   changes in that release (pin wrapping, RP2350B upper-bank pins, `side_pindir`,
   DMA stop-on-free) don't touch this code. Anything from ~v1.20 on should work;
   there's no reason not to take the latest.
2. Hold **BOOT** on the RP2040-Zero, plug in USB, release. An `RPI-RP2` drive
   appears.
3. Drag the `.uf2` onto it. The board reboots as a serial device.
   The `RPI-RP2` drive disappearing is success, not a failure — the board has
   rebooted out of the bootloader.

4. **MicroPython is a serial port, not a drive.** BOOTSEL and `RPI-RP2` are only
   ever for flashing `.uf2` firmware. Once MicroPython is on the board there is
   no folder to drag `.py` files into; you copy them over the serial connection.
   Do *not* re-enter BOOTSEL to load code.

   On this machine the board enumerates as **COM6** (`VID_2E8A&PID_0005` — the
   `0005` product ID is the MicroPython CDC interface; `0003` would mean it is
   still in bootloader mode). To find it again after a replug:
   ```
   powershell "Get-CimInstance Win32_PnPEntity | ? { $_.Name -match 'COM\d+' } | ft Name"
   ```

5. Install the host tool once, then copy and run. Paths below are relative to
   the **project root**, so they work straight from the PowerShell prompt you
   land in:
   ```
   python3 -m pip install --user mpremote
   python3 -m mpremote connect COM6 fs cp firmware\rp2040\encoder_test.py :encoder_test.py
   python3 -m mpremote connect COM6 run firmware\rp2040\hand_test.py
   ```
   Ctrl-C stops it. `python3 -m mpremote connect COM6 repl` drops you at a prompt.

   Nothing in this directory runs on the PC. `rp2` is the RP2040's PIO module and
   exists only in MicroPython firmware, so `python3 hand_test.py` on Windows will
   always fail with `ModuleNotFoundError: No module named 'rp2'`. That is the
   expected result, not a broken install — the code has to run *on the chip*.
   `mpremote` is the bridge: `connect COM6` opens the serial link, `run <file>`
   ships the local file to the board and executes it there, and the board's
   output comes back to your terminal.

   This is also why `hand_test.py` can `from encoder_test import ...` — that
   resolves against the board's filesystem, where step 5 copied it, not against
   the project folder.

   Two PowerShell gotchas: the tool is `mpremote`, one word (typing `mp remote`
   makes PowerShell resolve `mp` to the `Move-ItemProperty` cmdlet and prompt you
   for parameters), and it is not on PATH, so always invoke it as
   `python3 -m mpremote`.

   Thonny (interpreter: MicroPython (Raspberry Pi Pico)) does the same thing with
   a GUI and is easier for poking at things interactively.

## Checking the encoder lines without spinning anything

Each pin is read once with a pull-up and once with a pull-down. A pin that
follows the pull is floating; one that ignores it is being driven by the encoder:

```
python -m mpremote connect COM6 exec "
import time
from machine import Pin
def probe(n):
    p = Pin(n, Pin.IN, Pin.PULL_UP);   time.sleep_ms(30); up = p.value()
    p = Pin(n, Pin.IN, Pin.PULL_DOWN); time.sleep_ms(30); dn = p.value()
    if up == 1 and dn == 0: return 'FLOATING (nothing connected)'
    if up == 0 and dn == 0: return 'driven LOW (or shorted to GND)'
    if up == 1 and dn == 1: return 'driven HIGH'
    return 'up=%d dn=%d ??' % (up, dn)
for n, name in ((10, 'GP10 / A'), (11, 'GP11 / B')):
    print('%-10s %s' % (name, probe(n)))
"
```

Both lines driven (rather than floating) means the encoder is wired and powered.
That also settles the `VERIFY encoder voltage` question: a hall output that can
actively drive is a powered, push-pull output, so 3.3V is sufficient and the
5V-plus-dividers fallback is not needed.

**Result on this build: both lines driven at 3.3V. Confirmed working.**

## Bench procedure

The worm gearbox is self-locking, so you can't backdrive the output shaft to
test by hand — the encoder is on the motor shaft ahead of the gearbox. Use low
voltage instead of hand-turning.

**Set the PSU current limit to ~0.5A before anything else.** An N20 free-runs
around 50–100 mA, so tripping into constant-current means a bind or a miswire,
which is useful signal.

1. **Motor leads disconnected.** Run the script. It prints the idle pin levels
   first — both should read 1 (internal pull-ups). Both stuck at 0 means Vcc or
   GND is wrong; fix that before going further.
2. **3V.** Dial it in with the leads open, confirm on a meter, *then* connect.
   The motor creeps. Counts should climb smoothly and `coherence` should sit
   near 100%.
3. **Swap the two motor leads.** The sign of `net/s` should flip. That confirms
   A/B phase order and tells you which direction is positive.
4. **6V, then 12V.** Watch whether `coherence` holds up as speed rises.

## Reading the output

```
  count     net/s   counts/s   coherence
   +1482    +742.0      742.0      100.0%
```

- `count` — signed total since start.
- `net/s` — net counts per second. Sign is direction.
- `counts/s` — gross, counting every reversal. Equals `|net/s|` for clean rotation.
- `coherence` — `|net| / gross`. **This is the noise detector.** Steady rotation
  sits near 100%. A high `counts/s` with low `coherence` means the counter is
  being jittered back and forth by electrical noise — that is the missing
  0.1 µF caps across the motor terminals, not a bug in the decoder. Expect it to
  degrade as you go from 3V to 12V until those caps are in.

With the motor stopped, `count` should be perfectly still. Any drift at rest is
noise pickup on the encoder lines.

## Measuring counts per revolution

`COUNTS_PER_OUTPUT_REV` is 0, which suppresses the RPM column. To fill it in:
mark the output shaft, run at 3V, and note `count` across a whole number of
output revolutions. Divide. Then set the constant and RPM starts printing.

For reference: this is a **2x** decoder (it counts both edges of A and uses B
for direction). A 7 PPR encoder therefore gives 14 counts per motor-shaft
revolution, multiplied by the gearbox ratio at the output.

## What this can't test

Direction control, PWM speed, and STBY all need the TB6612, so there's no
closed loop yet. What it does retire: encoder works at 3.3V, phase order and
sign, counts per revolution, the PIO decoder itself, and how much noise
immunity you actually have.

## Notes on the decoder

Decoding runs in PIO, so counts aren't lost at speed — Python only polls a
counter. The RP2040's `jmp_pin` and `in_base` are independent, which is the
trick that frees scratch register X to be the counter: A is tested via `jmp_pin`
for edges, B is read via `in_base` for direction.

Reading the count drains the RX FIFO and then takes one more sample. The drained
entries can be arbitrarily old; the one read afterwards was pushed by the polling
loop after the drain, so it is current.

Port the PIO program to C when you set up the SDK for the real system — the
program itself transfers unchanged.
