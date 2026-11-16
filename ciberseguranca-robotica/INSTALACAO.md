# INSTALACAO.md — build ciberseg-esp32 from scratch on a fresh VS Code

This guide gathers **everything** needed to recreate the project on a new computer
and get the three boards (plus the monitor-mode spy) working: hardware,
firmwares, tools, libraries, extensions and VS Code configuration, and the
flashing commands for each file.

> Pedagogical vision and lesson plan: [README.md](README.md), [arduino/README.md](arduino/README.md)
> and the study guide in [docs/](docs/). This file covers only **installation and running**.

---

## 1. Overview

```
[CONTROLLER Stamp S3 + 2 buttons] --ESP-NOW (channel 1)--> [ROBOT Capsule] --BLE--> [LEGO motor]
                                        |
                  [SPY M5StickC PlusSE]  (MicroPython, broadcast, screen)
                  [SPY monitor XIAO C6]  (Arduino/C, promiscuous mode, captures unicast)
```

Two worlds of code live in the repository:

| Folder | Language | How it gets onto the board |
|-------|-----------|-----------------------|
| [micropython/](micropython/) | MicroPython | `mpremote` copies the `.py` as `main.py` |
| [arduino/](arduino/) | C++ (Arduino/ESP-IDF) | `arduino-cli` compiles and flashes the `.ino` |

The computer is only used to **flash**. After that each board runs on its own on a battery/power bank.

---

## 2. Hardware

| Role | Board | Firmware | Notes |
|-------|-------|----------|-------------|
| Controller | **M5Stamp S3** + Breakout v2 + 2 buttons | MicroPython (official or UiFlow2) | GPIO19/20 are the USB: **never** use them for buttons. RGB LED on GPIO21 |
| Robot | **M5Stack Capsule** (ESP32-S3) | **UiFlow2** (filesystem in `/flash`) | talks BLE to the LEGO motor |
| Motor | **LEGO Education Double Motor** + Connection Card | updated LEGO firmware | does not work while charging |
| Spy (screen) | **M5StickC PlusSE** | **UiFlow2** (uses the `m5` module) | button A = GPIO37, B = GPIO39 |
| Monitor spy | **Seeed XIAO ESP32-C6** | Arduino (flashed with `arduino-cli`) | LED GPIO15 (active low), BOOT GPIO9 |
| Monitor spy (alternatives) | StickC Plus2/PlusSE or Capsule | Arduino | replaces the board's MicroPython |

Also: **USB data cables** (not "charge-only") and power banks.

---

## 3. Software on the computer

Tested on macOS with these versions:

| Tool | Tested version | What for |
|------------|----------------|----------|
| Python | 3.13 | run `mpremote` |
| `mpremote` | 1.29.0 | copy files, run scripts, install `aioble` on the MicroPython boards |
| `arduino-cli` | 1.6.0 | compile and flash the `.ino` files |
| Core **esp32:esp32** (Espressif) | 3.3.8 | ESP32/S3/C6 toolchain for Arduino |
| Library **M5Unified** | 0.2.14 | only in the M5 sketches (StickC / Capsule) |
| Library **M5GFX** | 0.2.20 | dependency of M5Unified (installed together) |
| Google Chrome | any recent | regenerate the study-guide PDF |
| M5Burner | current | flash the UiFlow2 firmware onto the M5 boards |

### 3.1 Python + mpremote

```bash
# macOS (Homebrew) — or install Python from python.org
brew install python
python3 -m pip install --upgrade mpremote
mpremote --version
```

Windows: `py -m pip install mpremote`. Linux: `pipx install mpremote` (and add the user
to the `dialout` group to access `/dev/ttyUSB*`/`/dev/ttyACM*`).

### 3.2 arduino-cli + ESP32 core + libraries

```bash
brew install arduino-cli          # Windows: winget install ArduinoSA.CLI

arduino-cli config init           # creates ~/Library/Arduino15/arduino-cli.yaml (mac)
arduino-cli config add board_manager.additional_urls \
  https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install esp32:esp32          # (or esp32:esp32@3.3.8 to pin the version)

arduino-cli lib install M5Unified             # pulls M5GFX along with it
```

Check that the FQBNs used in the project exist:

```bash
arduino-cli board listall esp32:esp32 | grep -iE 'XIAO_ESP32C6|stickc_plus2|capsule|stamp_s3'
```

| Board | FQBN |
|-------|------|
| XIAO ESP32-C6 | `esp32:esp32:XIAO_ESP32C6` |
| M5StickC Plus2 / PlusSE | `esp32:esp32:m5stack_stickc_plus2` |
| M5 Capsule | `esp32:esp32:m5stack_capsule` |
| M5Stamp S3 (if ever done in Arduino) | `esp32:esp32:m5stack_stamp_s3` |

> Warning: the **`esp32:esp32`** core (Espressif) is the right one. The `arduino:esp32` ("Arduino ESP32
> Boards", from Arduino itself) does **not** have these FQBNs — do not use it.

> The sketches use the 3.x core API (`esp_now_send`, `esp_wifi_set_promiscuous`, etc.).
> With the 2.x core the compile may fail.

### 3.3 USB drivers

- ESP32-S3 and ESP32-C6 (Stamp S3, Capsule, XIAO C6) use **native USB**: they show up as
  `/dev/cu.usbmodem*` (mac) or `COMx` (Windows), with no driver.
- The M5StickC uses a USB-serial converter: it shows up as `/dev/cu.usbserial-*`. On recent
  macOS the driver already ships with the system; if it does not appear, install the **CH9102/CH34x**
  driver from the M5Stack/WCH site. On Windows, the same driver.

### 3.4 Board firmwares (once per board)

| Board | Firmware | How to flash |
|-------|----------|-------------|
| Capsule (robot) | **UiFlow2** | M5Burner → pick the board → *Burn* |
| StickC PlusSE (screen spy) | **UiFlow2** | M5Burner. Brings the `m5/` folder used by `espiao.py` |
| Stamp S3 (controller) | Official MicroPython (`ESP32_GENERIC_S3`) **or** UiFlow2 | MicroPython: `esptool.py --chip esp32s3 erase_flash` and `write_flash 0 firmware.bin` (from micropython.org/download). UiFlow2: M5Burner |
| XIAO C6 (monitor spy) | nothing beforehand | `arduino-cli upload` flashes the whole firmware |

The encrypted scripts (`*_cripto.py`) use `cryptolib`, which exists in both UiFlow2 and
the official MicroPython for ESP32.

**How to know where to write `main.py`:**

```bash
mpremote connect <port> fs ls :
# if you see "flash/"  -> UiFlow2: write to :/flash/main.py
# otherwise            -> plain MicroPython: write to :main.py
```

---

## 4. VS Code

### 4.1 Extensions

| Extension | ID | What for |
|----------|----|----------|
| Python | `ms-python.python` | editing the `.py` files |
| Pylance | `ms-python.vscode-pylance` | analysis (disabled under `micropython/`, see below) |
| C/C++ | `ms-vscode.cpptools` | editing the `.ino` files (basic IntelliSense) |
| PDF viewer (optional) | `tomoki1207.pdf` | open the study guide in the editor |
| Arduino (optional) | `vscode-arduino.vscode-arduino-community` | compile/flash buttons in the bar; the *tasks* below already handle it without this |

So that VS Code suggests these extensions to whoever opens the project, create
`.vscode/extensions.json`:

```json
{
  "recommendations": [
    "ms-python.python",
    "ms-python.vscode-pylance",
    "ms-vscode.cpptools",
    "tomoki1207.pdf"
  ]
}
```

### 4.2 `.vscode/settings.json` (already in the repository)

```json
{
  "python.analysis.exclude": ["**/micropython/**", "**/legado/**"],
  "files.associations": {
    "*.py": "python",
    "*.ino": "cpp"
  },
  "python-envs.defaultEnvManager": "ms-python.python:system"
}
```

- `python.analysis.exclude`: Pylance does not know `network`, `espnow`, `machine`,
  `cryptolib`, `aioble`, `m5`… (they only exist in the firmware). Excluding the folder avoids
  hundreds of false warnings. **This is expected.**
- `"*.ino": "cpp"` (optional): makes VS Code treat the sketch as C++. The ESP-IDF includes
  (`esp_wifi.h`, `esp_now.h`) will show up underlined — the real compilation is done by
  `arduino-cli`, so you can ignore it.

### 4.3 `.vscode/tasks.json` — flash from VS Code (Ctrl/Cmd+Shift+P → *Run Task*)

Copy it into `.vscode/tasks.json`. The tasks ask for the port (and, for Arduino, the sketch and FQBN)
each time they run.

```json
{
  "version": "2.0.0",
  "inputs": [
    { "id": "porta", "type": "promptString",
      "description": "Serial port (e.g. /dev/cu.usbmodem101, COM5)" },
    { "id": "sketch", "type": "pickString", "description": "Arduino sketch",
      "options": [
        "arduino/espiao_monitor_xiao",
        "arduino/espiao_monitor_xiao_cif",
        "arduino/espiao_monitor_capsule",
        "arduino/espiao_monitor"
      ] },
    { "id": "fqbn", "type": "pickString", "description": "Board (FQBN)",
      "options": [
        "esp32:esp32:XIAO_ESP32C6",
        "esp32:esp32:m5stack_capsule",
        "esp32:esp32:m5stack_stickc_plus2"
      ] },
    { "id": "destino", "type": "pickString", "description": "main.py destination",
      "options": [":main.py", ":/flash/main.py"] }
  ],
  "tasks": [
    { "label": "Listar portas",
      "type": "shell",
      "command": "mpremote connect list && arduino-cli board list",
      "problemMatcher": [] },

    { "label": "Arduino: compilar",
      "type": "shell",
      "command": "arduino-cli compile --fqbn ${input:fqbn} ${input:sketch}",
      "problemMatcher": ["$gcc"], "group": "build" },
    { "label": "Arduino: compilar e gravar",
      "type": "shell",
      "command": "arduino-cli compile --upload -p ${input:porta} --fqbn ${input:fqbn} ${input:sketch}",
      "problemMatcher": ["$gcc"] },
    { "label": "Arduino: monitor serial 115200",
      "type": "shell",
      "command": "arduino-cli monitor -p ${input:porta} -c baudrate=115200",
      "isBackground": true, "problemMatcher": [] },

    { "label": "MicroPython: gravar arquivo aberto como main.py",
      "type": "shell",
      "command": "mpremote connect ${input:porta} fs cp \"${file}\" ${input:destino} + reset",
      "problemMatcher": [] },
    { "label": "MicroPython: rodar arquivo aberto (sem gravar)",
      "type": "shell",
      "command": "mpremote connect ${input:porta} run \"${file}\"",
      "problemMatcher": [] },
    { "label": "MicroPython: REPL",
      "type": "shell",
      "command": "mpremote connect ${input:porta} repl",
      "problemMatcher": [] },
    { "label": "MicroPython: preparar robô (aioble + lego_motor)",
      "type": "shell",
      "command": "mpremote connect ${input:porta} mip install --target=/flash/libs aioble + fs cp micropython/robo/lego_motor.py :/flash/lego_motor.py",
      "problemMatcher": [] },

    { "label": "Docs: regerar PDF do guia",
      "type": "shell",
      "command": "\"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome\" --headless=new --no-pdf-header-footer --print-to-pdf=docs/guia-de-estudo-ciberseg-esp32.pdf docs/guia-de-estudo.html",
      "problemMatcher": [] }
  ]
}
```

> **One port = one program.** Close the terminal running `monitor`/`repl` (or the Thonny/Arduino IDE)
> before flashing, otherwise you get `could not enter raw repl` or `port busy`.

> The task labels above are kept in Portuguese to match the lesson materials; translate them
> freely if you prefer.

### 4.4 IntelliSense for the `.ino` files (optional)

`arduino-cli` generates the compilation database, which the C/C++ extension reads:

```bash
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32C6 \
  --only-compilation-database --build-path build/xiao arduino/espiao_monitor_xiao
```

Then, in `.vscode/c_cpp_properties.json`:

```json
{
  "configurations": [
    { "name": "ESP32 (arduino-cli)",
      "compileCommands": "${workspaceFolder}/build/xiao/compile_commands.json" }
  ],
  "version": 4
}
```

Put `build/` in `.gitignore`.

---

## 5. File descriptions

### 5.1 `micropython/` — runs on the MicroPython boards

| File | Board | What it does | Depends on |
|---------|-------|-----------|------------|
| [controle/controle.py](micropython/controle/controle.py) | Stamp S3 | buttons → `F`/`T`/`P` in **broadcast**, clear text; RGB LED shows the command | `PINO_FRENTE`, `PINO_TRAS`, `ATIVO_EM` |
| [controle/controle_unicast.py](micropython/controle/controle_unicast.py) | Stamp S3 | same, but **unicast** to `ROBO_MAC` | `ROBO_MAC` |
| [controle/controle_cripto.py](micropython/controle/controle_cripto.py) | Stamp S3 | encrypts AES-128 (ECB, byte 0 = command + 15 random) and sends unicast | `ROBO_MAC`, `CHAVE`, `cryptolib` |
| [espiao/espiao.py](micropython/espiao/espiao.py) | StickC PlusSE | listens to broadcast, shows the history on the screen; A = replay, B = selection. **Do not change** | the board's `m5/` folder |
| [espiao/espiao_cripto.py](micropython/espiao/espiao_cripto.py) | StickC PlusSE | shows the ciphertext in hex and replays it; only sees broadcast | the board's `m5/` folder |
| [robo/robo.py](micropython/robo/robo.py) | Capsule | receives `F/T/E/D/P` from anyone and calls `run_tank()` on the motor | `lego_motor.py`, `aioble`, `CARD_SERIAL` |
| [robo/robo_cripto.py](micropython/robo/robo_cripto.py) | Capsule | decrypts the AES block and moves | same + `CHAVE`, `cryptolib` |
| [robo/lego_motor.py](micropython/robo/lego_motor.py) | Capsule | BLE driver for the LEGO Education motor (scan by Connection Card, RPC) | `aioble`, `bluetooth` |
| [ferramentas/descobre_pinos.py](micropython/ferramentas/descobre_pinos.py) | Stamp S3 | prints which GPIO changes when you press each button | — |
| [ferramentas/mostra_mac.py](micropython/ferramentas/mostra_mac.py) | robot | prints `ROBO_MAC = b'...'` ready to paste | — |
| [ferramentas/teste_motor.py](micropython/ferramentas/teste_motor.py) | robot | spins the motor for 1 s (tests just the BLE) | `lego_motor.py`, `aioble` |

**MicroPython libraries:** all ship in the firmware (`network`, `espnow`, `machine`,
`time`, `os`, `uasyncio`, `bluetooth`, `cryptolib`), except:

- **`aioble`** — install it on the robot: `mpremote connect <port> mip install --target=/flash/libs aioble`;
- **`m5`** (`m5_display`) — ships with the StickC's UiFlow2. **Not in the repository.** Back it up:
  `mpremote connect <spy-port> fs cp -r :m5 micropython/espiao/`.

### 5.2 `arduino/` — monitor-mode spy (only exists in C)

MicroPython does not expose `esp_wifi_set_promiscuous`; that is why this node is Arduino.

| Sketch | Board / FQBN | Output | Libraries |
|--------|--------------|-------|------------|
| [espiao_monitor/](arduino/espiao_monitor/espiao_monitor.ino) | StickC Plus2/PlusSE — `esp32:esp32:m5stack_stickc_plus2` | screen: history; A = replay, B = selection | M5Unified |
| [espiao_monitor_capsule/](arduino/espiao_monitor_capsule/espiao_monitor_capsule.ino) | Capsule — `esp32:esp32:m5stack_capsule` | RGB LED (GPIO21) + Serial; button = replay | M5Unified |
| [espiao_monitor_xiao/](arduino/espiao_monitor_xiao/espiao_monitor_xiao.ino) | XIAO C6 — `esp32:esp32:XIAO_ESP32C6` | Serial + LED; BOOT replays the last **movement**. **Fails against the cipher** (on purpose) | core only |
| [espiao_monitor_xiao_cif/](arduino/espiao_monitor_xiao_cif/espiao_monitor_xiao_cif.ino) | XIAO C6 — `esp32:esp32:XIAO_ESP32C6` | Serial + LED; BOOT tap = **verbatim** replay, hold = previous frame. Works against the cipher | core only |
| [espiao_monitor_xiao_term/](arduino/espiao_monitor_xiao_term/espiao_monitor_xiao_term.ino) | XIAO C6 — `esp32:esp32:XIAO_ESP32C6` | **terminal-controlled** (Serial 115200): numbered history (`UNI`/`BCAST`, MAC, RSSI, hex), replay the chosen packet (`<n>`, `<n> xK`, `u`, `l`); BOOT = replay last. Verbatim, so it works clear, unicast and encrypted. **The recommended spy for stages 2–4** | core only |

They all include `WiFi.h`, `esp_wifi.h`, `esp_now.h` (from the esp32 core) and have
`CANAL = 1` and `ROBO_MAC[6]` to fill in at the top.

> Arduino rule: the folder and the `.ino` have the **same name**. That is why each sketch has its own folder.

### 5.3 Others

| Path | What it is |
|---------|---------|
| [README.md](README.md) | overview, demo and pedagogical progression |
| [CLAUDE.md](CLAUDE.md) | project conventions (channel, commands, structure) |
| [arduino/README.md](arduino/README.md) | details of the monitor mode and lesson plans A and B |
| [docs/guia-de-estudo.html](docs/guia-de-estudo.html) → `.pdf` | study guide (HTML source, PDF generated by Chrome) |
| [legado/](legado/) | old projects; not needed for the current system |
| [.vscode/settings.json](.vscode/settings.json) | excludes `micropython/` and `legado/` from Pylance |

---

## 6. Conventions that must match across the boards

| Item | Value | Where |
|------|-------|-------|
| Wi-Fi/ESP-NOW channel | `CANAL = 1` | all `.py` and `.ino` |
| Broadcast | `b'\xff' * 6` / `{0xFF,…}` | controller, spies |
| Commands | `F` forward, `T` back, `E` left, `D` right, `P` stop | all |
| Radio | `sta.config(pm=sta.PM_NONE)` and `e.config(rxbuf=2048)` before `e.active(True)` | MicroPython |
| Robot MAC | `ROBO_MAC` | `controle_unicast.py`, `controle_cripto.py`, all `.ino` |
| AES key (16 bytes) | `CHAVE = b"ciberseg-aes-key"` | `controle_cripto.py` **and** `robo_cripto.py` (identical) |
| Connection Card | `CARD_SERIAL = "7551"` | `robo.py`, `robo_cripto.py`, `teste_motor.py` |

---

## 7. Step by step to get everything running

Open the folder in VS Code and use the integrated terminal (`` Ctrl+` ``) at the project root.

### 7.0 Find the ports

```bash
mpremote connect list
arduino-cli board list
# which MicroPython board is on each port:
for p in /dev/cu.usbmodem* /dev/cu.usbserial*; do printf "%s: " $p; \
  mpremote connect $p exec "import sys;print(sys.implementation._machine)"; done
```

Plug in **one board at a time** the first time and note down each one's port.

### 7.1 Robot (Capsule, UiFlow2)

```bash
mpremote connect <robot-port> run micropython/ferramentas/mostra_mac.py   # note the ROBO_MAC
mpremote connect <robot-port> mip install --target=/flash/libs aioble
mpremote connect <robot-port> fs cp micropython/robo/lego_motor.py :/flash/lego_motor.py
# isolated motor test (motor on, OFF the charger):
mpremote connect <robot-port> run micropython/ferramentas/teste_motor.py
# flash the robot program:
mpremote connect <robot-port> fs cp micropython/robo/robo.py :/flash/main.py + reset
```

First, set `CARD_SERIAL` in `robo.py`. If a wheel spins the wrong way: `INVERTER_ESQUERDO` / `INVERTER_DIREITO`.

### 7.2 Controller (Stamp S3)

```bash
mpremote connect <controller-port> run micropython/ferramentas/descobre_pinos.py
```

Press each button, fill in `PINO_FRENTE`, `PINO_TRAS` and `ATIVO_EM` (`1 -> 0` ⇒ `ATIVO_EM = 0`;
`0 -> 1` ⇒ `ATIVO_EM = 1`) in `controle.py` (and in the unicast/cripto versions). Then:

```bash
mpremote connect <controller-port> fs cp micropython/controle/controle.py :main.py + reset
```

(Use `:/flash/main.py` if the Stamp is running UiFlow2.)

### 7.3 Screen spy (StickC PlusSE, UiFlow2)

```bash
mpremote connect <spy-port> fs cp -r :m5 micropython/espiao/     # backup, once
mpremote connect <spy-port> fs cp micropython/espiao/espiao.py :main.py + reset
```

### 7.4 Monitor-mode spy (XIAO ESP32-C6, Arduino)

1. Paste the `ROBO_MAC` from step 7.1 into `ROBO_MAC[6]` at the top of the `.ino`
   (e.g.: `{ 0x48, 0x27, 0xe2, 0xe3, 0xac, 0x78 }`).
2. Compile and flash:

```bash
arduino-cli compile --upload -p <xiao-port> --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao_term
arduino-cli monitor  -p <xiao-port> -c baudrate=115200
```

`espiao_monitor_xiao_term` is the **recommended** one: it works for stages 2, 3 and 4 without
re-flashing. In the monitor, type `h` for help, `l` to list the captures, and `<n>` / `<n> xK` to
replay a packet (the last is the availability flood). The older `espiao_monitor_xiao` (reads the
command, fails against the cipher) and `espiao_monitor_xiao_cif` (replays verbatim, button-driven)
stay in the repo for the lesson that contrasts them.

For the StickC or the Capsule, swap the FQBN and folder (see table 5.2). Flashing an Arduino
sketch **erases the MicroPython** on the board; to go back, re-flash UiFlow2 with M5Burner.

### 7.5 Switch lesson stages

| Stage (CIA leg) | Controller | Robot | Spy that captures / replays |
|-----------------|-----------|-------|------------------------------|
| 1. Broadcast, clear (C) | `controle.py` | `robo.py` | `espiao.py` (StickC) or any monitor sketch |
| 2. Unicast, clear (C) | `controle_unicast.py` | `robo.py` | monitor only — `espiao_monitor_xiao_term` (terminal) |
| 3. Unicast, encrypted (C/I) | `controle_cripto.py` | `robo_cripto.py` | `espiao_monitor_xiao_term` replays the ciphertext verbatim; `espiao_monitor_xiao` **fails** (it tries to read) |
| 4. Availability (A) | any of the above | — | on the terminal spy, replay the **stop** packet K times (`<n> xK`, e.g. `7 x10`) → the robot stutters/freezes (DoS) |

```bash
mpremote connect <controller-port> fs cp micropython/controle/controle_cripto.py :main.py + reset
mpremote connect <robot-port>      fs cp micropython/robo/robo_cripto.py        :/flash/main.py + reset
```

To go back to clear text, re-flash `controle.py` (or `controle_unicast.py`) and `robo.py`.

**Availability attack (stage 4).** On the `espiao_monitor_xiao_term` terminal, list the captures
(`l`), find the **stop** packet (in the clear versions it shows as `PARAR`; encrypted, it is the
`? (ilegivel)` frame captured right when the robot stopped) and replay it K times, e.g. `7 x10`.
The robot keeps being told to stop, so it **stutters / freezes** while the controller is trying to
drive it — a denial of service. No key needed: encryption hid the command's content, not the fact
that the robot stopped. The defense (HMAC + a sequence number/nonce) also kills this, because the
robot rejects the repeated frames; but a raw channel flood cannot be fully prevented — **availability
is the hardest leg of the triad**.

### 7.6 Demo

1. Power the LEGO motor (off the charger) and the robot; wait for the BLE connection.
2. Power the spies (screen: `ESPIAO ... ouvindo`; XIAO: open the serial monitor).
3. Press FRENTE on the controller: the robot moves and the spy logs it.
4. Release. On the spy, select the captured `FRENTE` and replay it: **the robot moves on its own**.

---

## 8. Common problems

| Symptom | Cause / fix |
|---------|-----------------|
| `could not enter raw repl` / `port busy` | port in use: close `monitor`, `repl`, Thonny, Arduino IDE |
| XIAO upload stops at `Connecting...` | hold **BOOT**, press **RESET**, release **BOOT**, run the upload again |
| XIAO flashed but the serial shows nothing | press RESET with the monitor open; if still silent, flash with `--board-options CDCOnBoot=cdc` |
| Robot does not find the motor | wrong `CARD_SERIAL` (the most common failure) or motor on the charger |
| RPC version error on the motor | update the firmware at code.legoeducation.com |
| `ImportError: aioble` | you missed `mip install --target=/flash/libs aioble` on the robot |
| `ImportError: m5` on the spy | the board does not have UiFlow2 or the `m5/` folder was erased: re-flash UiFlow2 |
| Nothing happens after `fs cp` | flashed to the wrong place (`:main.py` × `:/flash/main.py`) or missing `+ reset` |
| Controller/spy in unicast see nothing | expected: only the **monitor-mode** spy sees unicast |
| Robot does not obey the encrypted controller | `CHAVE` differs between controller and robot, or wrong `ROBO_MAC` |
| `arduino-cli`: unknown FQBN | wrong core: install `esp32:esp32` (Espressif) with the URL from item 3.2 |
| Pylance full of warnings under `micropython/` | missing the `python.analysis.exclude` in `.vscode/settings.json` |
| Board does not show up in the port list | charge-only cable, or missing CH9102/CH34x driver (StickC) |
| Controller freezes when using GPIO19/20 | those are the Stamp S3's USB: pick other pins |

---

## 9. Quick checklist for a new computer

- [ ] Python 3 + `pip install mpremote`
- [ ] `arduino-cli` + the Espressif URL + `core install esp32:esp32` + `lib install M5Unified`
- [ ] VS Code + Python, Pylance, C/C++ extensions
- [ ] `.vscode/` already ships in the repo (`settings.json`, `tasks.json`, `extensions.json`, `c_cpp_properties.json`)
- [ ] Run the **Arduino: generate IntelliSense (XIAO)** step once (creates `build/xiao/compile_commands.json`)
- [ ] M5Burner with UiFlow2 on the Capsule and the StickC; MicroPython or UiFlow2 on the Stamp S3
- [ ] `aioble` + `lego_motor.py` on the robot; backup of the spy's `m5/` folder
- [ ] `ROBO_MAC`, `CARD_SERIAL`, `PINO_FRENTE`/`PINO_TRAS`/`ATIVO_EM`, `CHAVE` checked
- [ ] USB data cables and power banks
