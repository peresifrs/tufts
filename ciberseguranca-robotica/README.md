# ciberseg-esp32

Cybersecurity with robotics for basic education (IFRS/POALab + Tufts/CEEO).
Three ESP32 boards talk over **ESP-NOW in broadcast and clear text** — deliberately
insecure — and a LEGO Education motor is the "robot". **Nothing depends on a computer**:
each board runs on its own on a battery/power bank. The PC is only used to flash.

```
 [CONTROLLER]  --ESP-NOW broadcast-->  [ROBOT]  --BLE-->  [LEGO motor]
  Stamp S3           "F" / "T" / "P"    Capsule
  2 buttons                 |
                            v  (everyone hears)
                        [SPY]  M5StickC PlusSE with a screen
                        sees the commands and REPLAYS -> the robot obeys
```

**The lesson:** the spy **reads** everything (confidentiality broken) and, by repeating a
captured command, the robot **obeys the impostor** (authenticity broken) — it has no way
to know who sent it.

> **Full study guide** (concepts, the three models, the spy's modes, commented code
> and lesson plan): [docs/guia-de-estudo-ciberseg-esp32.pdf](docs/guia-de-estudo-ciberseg-esp32.pdf).
> The source is [docs/guia-de-estudo.html](docs/guia-de-estudo.html). To regenerate the PDF after editing:
> `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --no-pdf-header-footer --print-to-pdf=docs/guia-de-estudo-ciberseg-esp32.pdf docs/guia-de-estudo.html`

## The three boards

| Node | Board | Folder | What it does |
|------|-------|--------|--------------|
| **Controller** | M5Stamp S3 + Breakout v2 | [micropython/controle/](micropython/controle/) | FORWARD button sends `F`, BACK button sends `T`, releasing sends `P` |
| **Spy** | M5StickC PlusSE (screen) | [micropython/espiao/](micropython/espiao/) | shows what was captured; button A = replay, button B = pick from the history |
| **Robot** | M5Stack Capsule | [micropython/robo/](micropython/robo/) | receives the command and moves the LEGO motor over BLE |

The code is MicroPython and runs the same on M5 and on XIAO ESP32-C6. Only the pins and
the filesystem path change.

## Flash (once per board)

```bash
cd ~/Documents/ifrs/VSCode/ciberseg-esp32
mpremote connect list                  # find each board's port
```

> **UiFlow2 firmware** (M5 with `/flash`): write to `:/flash/main.py`.
> **Plain MicroPython**: write to `:main.py`. When in doubt: `mpremote connect <port> fs ls :`.

### Robot (Capsule)
```bash
mpremote connect <robot-port> mip install --target=/flash/libs aioble
mpremote connect <robot-port> fs cp micropython/robo/lego_motor.py :/flash/lego_motor.py
mpremote connect <robot-port> fs cp micropython/robo/robo.py :/flash/main.py
```
Set `CARD_SERIAL` in `robo.py` to the Connection Card number (default `7551`).
If a wheel spins the wrong way, use `INVERTER_ESQUERDO` / `INVERTER_DIREITO`.

### Spy (M5StickC PlusSE)
```bash
mpremote connect <spy-port> fs cp micropython/espiao/espiao.py :main.py
```
The `m5/` folder (screen driver) is **already on the board and is not in the repository**.
Back it up once: `mpremote connect <spy-port> fs cp -r :m5 micropython/espiao/`.

### Controller (Stamp S3 + Breakout v2)
1. Find the buttons' GPIOs:
   ```bash
   mpremote connect <controller-port> run micropython/ferramentas/descobre_pinos.py
   ```
   Press each button and note the GPIO that shows up.
2. Fill in `PINO_FRENTE` and `PINO_TRAS` at the top of `micropython/controle/controle.py`.
   If you see `1 -> 0`, keep `ATIVO_EM = 0`. If you see `0 -> 1`, change it to `ATIVO_EM = 1`.
3. Flash:
   ```bash
   mpremote connect <controller-port> fs cp micropython/controle/controle.py :main.py
   ```
The Stamp's RGB LED shows the command: green = forward, red = back, blue = stopped.

## Demo
1. Power the LEGO motor (off the charger) and the robot. Wait for the BLE connection.
2. Power the spy. The screen shows `ESPIAO ... ouvindo`.
3. Power the controller. Press FORWARD: the robot moves and the spy shows `FRENTE`.
4. Release and watch the robot stop. On the spy, select `FRENTE` with B and press A: **the robot moves on its own**.

## Two controller versions: broadcast and unicast

There are two **controller** versions, to contrast "everyone hears" with
"addressed to a single one". The **robot does not change** between them (it receives from
any sender); only the controller changes.

| Version | File | How it sends | Broadcast spy (StickC) | Monitor sniffer |
|---------|------|--------------|------------------------|-----------------|
| Broadcast | [controle.py](micropython/controle/controle.py) | to everyone (`b'\xff'*6`) | **captures** | captures |
| Unicast | [controle_unicast.py](micropython/controle/controle_unicast.py) | only to the robot's MAC | **does not capture** | **captures** (reads the air) |

The unicast version needs the robot's MAC in `ROBO_MAC`. Find it with:
```bash
mpremote connect <robot-port> run micropython/ferramentas/mostra_mac.py
# paste the line "ROBO_MAC = b'...'" at the top of controle_unicast.py
```

### Switch the version flashed on the controller

The controller is the **AtomS3 / Stamp S3**. Since the port names swap roles,
confirm which one it is before flashing:
```bash
for p in /dev/cu.usbmodem*; do printf "%s: " $p; mpremote connect $p exec "import sys;print(sys.implementation._machine)"; done
```

Broadcast:
```bash
mpremote connect <controller-port> fs cp micropython/controle/controle.py :main.py + reset
```
Unicast:
```bash
mpremote connect <controller-port> fs cp micropython/controle/controle_unicast.py :main.py + reset
```

> The `+ reset` restarts the board to run the new `main.py`. After a diagnostic `exec`,
> use `+ reset` too so the board goes back to running its program.

## Monitor-mode spy (captures the unicast)

With the controller in unicast, the broadcast MicroPython spy stops seeing the traffic.
A sniffer in **monitor (promiscuous) mode** reads the whole channel and captures the unicast
anyway — and this **only exists in C (Arduino)**, not in MicroPython (the firmware does not
expose monitor mode). Lesson: addressing ≠ encrypting.

**In versions 2 (unicast) and 3 (encryption) the spy is the XIAO C6 with `espiao_monitor_xiao_term`,
controlled by the terminal:** it lists the numbered captures (`UNI`/`BCAST`, MAC, RSSI, hex) and the
student picks which one to replay (`3`, `3 x5`, `u`, `l`). In VS Code: the **Espião XIAO: terminal** task.

```bash
mpremote connect <controller-port> fs cp micropython/controle/controle_unicast.py :main.py + reset
arduino-cli compile --upload -p <xiao-port> --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao_term
arduino-cli monitor -p <xiao-port> -c baudrate=115200
```

Ready-made variants in [arduino/](arduino/) (see [arduino/README.md](arduino/README.md)):
- `arduino/espiao_monitor/` — board with a screen (StickC), history + replay by button.
- `arduino/espiao_monitor_capsule/` — M5 Capsule (RGB LED + Serial).
- `arduino/espiao_monitor_xiao_term/` — XIAO ESP32-C6, **controlled by the terminal** (version 2): numbered history and replay of the chosen packet; verbatim, so it works against the cipher too.
- `arduino/espiao_monitor_xiao/` — XIAO ESP32-C6 (Serial + LED), **the easiest to flash**. Reads the command (F/T/E/D) and replays the last movement — **fails against the cipher** (use it to show the spy that cannot replay).
- `arduino/espiao_monitor_xiao_cif/` — same board, but replays the frame **verbatim** (tap = selected, hold = previous), so it **works even encrypted**.

Flash with arduino-cli (XIAO C6 example):
```bash
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao
arduino-cli upload -p <port> --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao
```

See the serial output (the Capsule/XIAO variants print the captures on the serial, at 115200):
```bash
arduino-cli monitor -p <port> -c baudrate=115200
```

## Encrypted version (confidentiality ≠ authenticity)

Now the controller **encrypts** the command (AES-128) and sends it **unicast** to the robot,
which **decrypts** it. Being unicast, only a spy in **monitor mode** captures the traffic:
the MicroPython spy is blind, as in the clear-text unicast. The spy **does not have the key**:
it cannot read the command (it only sees scrambled bytes).
**But it can still repeat** — it captures the ciphertext and resends the same bytes; the robot
decrypts and obeys. Encrypting gives **confidentiality, not authenticity**. The defense
(next version) is HMAC + a sequence number/nonce against replay.

Unlike the other versions, here the controller and the robot are a **matched pair**: they are
switched together, the `CHAVE` (16 bytes) must be identical on both, and the controller's `ROBO_MAC`
is the same as in `controle_unicast.py`:

| Node | File |
|------|------|
| Controller | [controle_cripto.py](micropython/controle/controle_cripto.py) (unicast to `ROBO_MAC`) |
| Robot | [robo_cripto.py](micropython/robo/robo_cripto.py) |
| Spy | [arduino/espiao_monitor_xiao_term/](arduino/espiao_monitor_xiao_term/) (terminal monitor mode; replays the ciphertext verbatim — **the same as version 2, no re-flashing**) |

```bash
mpremote connect <controller-port> fs cp micropython/controle/controle_cripto.py :main.py + reset
mpremote connect <robot-port>     fs cp micropython/robo/robo_cripto.py       :/flash/main.py
arduino-cli monitor -p <xiao-port> -c baudrate=115200      # XIAO already has espiao_monitor_xiao_term
```
In the terminal the packets show up as `16B  ? (ilegivel)  3fa1c9...`: the spy cannot read the
command, but `1` + Enter replays #1 and the robot obeys.

> [espiao_cripto.py](micropython/espiao/espiao_cripto.py) (StickC, shows the ciphertext in hex)
> only captures ciphertext sent in broadcast. Against the encrypted unicast controller it stays
> in `ouvindo` — the same thing that happens with `espiao.py` in clear-text unicast.

> The `CHAVE` is hard-coded only because it is didactic — **it is not secure** (anyone who reads
> the repository has the key). The point of the lesson is the replay, not key management.
> To go back to clear text, re-flash `controle.py` (or `controle_unicast.py`) and `robo.py`.

To demonstrate this with the monitor spy (XIAO) there are two deliberate versions —
one that reads the command and **fails** against the cipher, another that replays **verbatim**
and works — with the step by step and the flashing commands in **Lesson plan B** of
[arduino/README.md](arduino/README.md).

## Availability: flooding the "stop" command (completes the CIA triad)

The same replay also gives the third leg of the triad — **availability**. With the terminal spy
you repeat a packet several times (`<n> xK`, e.g. `7 x10`). Repeating the **"stop"** packet keeps
interrupting the controller: the robot **stutters / freezes intermittently** — a denial of service.
The attacker does not even need to read the command: in the encrypted version the "stop" frame is
identified by **behavior** (the robot stops) and replayed. Encryption hid the content, not the timing.

> **The defense and its honest limit:** HMAC + a sequence number/nonce also kills this flood —
> the robot rejects the repeated frames (a `seq` it has already seen). But a **raw channel flood**
> (sending as fast as possible to saturate the radio) cannot be fully prevented at the application
> layer. **Availability is the hardest leg of the triad**: you raise the cost of the attack, you do
> not eliminate it.

## Tools
- [descobre_pinos.py](micropython/ferramentas/descobre_pinos.py): shows which GPIO changes when you press a button.
- [mostra_mac.py](micropython/ferramentas/mostra_mac.py): prints the board's MAC (use it on the robot to fill in `ROBO_MAC`).
- [teste_motor.py](micropython/ferramentas/teste_motor.py): spins the LEGO motor for 1 s, to test the BLE on its own.

## Common problems
- `could not enter raw repl`: the port is busy (close Thonny or another REPL).
- The robot does not find the motor: check `CARD_SERIAL`; the motor does not work while on the charger.
- RPC version error on the motor: update the firmware at code.legoeducation.com.
- Use **data** USB cables, not "charge-only" ones.

## Legacy
[legado/](legado/) keeps copies of the old projects (`ciberseg-lego`, `ciberseg-m5`,
`lego-esp32-micropython`): the PC-bridge version, the keyboard MITM and the unicast/encrypted
ideas. None of it is needed for the current system.
