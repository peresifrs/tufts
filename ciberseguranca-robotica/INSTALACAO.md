# INSTALACAO.md — montar o ciberseg-esp32 do zero num VS Code novo

Este guia junta **tudo** o que é preciso para recriar o projeto num computador novo
e fazer as três placas (mais o espião em modo monitor) funcionarem: hardware,
firmwares, ferramentas, bibliotecas, extensões e configuração do VS Code, e os
comandos de gravação de cada arquivo.

> Visão pedagógica e roteiro de aula: [README.md](README.md), [arduino/README.md](arduino/README.md)
> e o guia de estudo em [docs/](docs/). Este arquivo trata só de **instalação e execução**.

---

## 1. Visão geral

```
[CONTROLE Stamp S3 + 2 botoes] --ESP-NOW (canal 1)--> [ROBO Capsule] --BLE--> [motor LEGO]
                                        |
                  [ESPIAO M5StickC PlusSE]  (MicroPython, broadcast, tela)
                  [ESPIAO monitor XIAO C6]  (Arduino/C, modo promiscuo, captura unicast)
```

Dois mundos de código convivem no repositório:

| Pasta | Linguagem | Como vai para a placa |
|-------|-----------|-----------------------|
| [micropython/](micropython/) | MicroPython | `mpremote` copia o `.py` como `main.py` |
| [arduino/](arduino/) | C++ (Arduino/ESP-IDF) | `arduino-cli` compila e grava o `.ino` |

O computador só serve para **gravar**. Depois disso cada placa roda sozinha na bateria/power bank.

---

## 2. Hardware

| Papel | Placa | Firmware | Observações |
|-------|-------|----------|-------------|
| Controle | **M5Stamp S3** + Breakout v2 + 2 botões | MicroPython (oficial ou UiFlow2) | GPIO19/20 são o USB: **nunca** use para botões. LED RGB no GPIO21 |
| Robô | **M5Stack Capsule** (ESP32-S3) | **UiFlow2** (filesystem em `/flash`) | fala BLE com o motor LEGO |
| Motor | **LEGO Education Double Motor** + Connection Card | firmware LEGO atualizado | não funciona no carregador |
| Espião (tela) | **M5StickC PlusSE** | **UiFlow2** (usa o módulo `m5`) | botão A = GPIO37, B = GPIO39 |
| Espião monitor | **Seeed XIAO ESP32-C6** | Arduino (gravado pelo `arduino-cli`) | LED GPIO15 (ativo baixo), BOOT GPIO9 |
| Espião monitor (alternativas) | StickC Plus2/PlusSE ou Capsule | Arduino | substitui o MicroPython da placa |

Mais: **cabos USB de dados** (não os "charge-only") e power banks.

---

## 3. Software no computador

Testado em macOS com estas versões:

| Ferramenta | Versão testada | Para quê |
|------------|----------------|----------|
| Python | 3.13 | rodar o `mpremote` |
| `mpremote` | 1.29.0 | copiar arquivos, rodar scripts, instalar `aioble` nas placas MicroPython |
| `arduino-cli` | 1.6.0 | compilar e gravar os `.ino` |
| Core **esp32:esp32** (Espressif) | 3.3.8 | toolchain ESP32/S3/C6 para o Arduino |
| Biblioteca **M5Unified** | 0.2.14 | só nos sketches para M5 (StickC / Capsule) |
| Biblioteca **M5GFX** | 0.2.20 | dependência do M5Unified (instala junto) |
| Google Chrome | qualquer recente | regerar o PDF do guia de estudo |
| M5Burner | atual | gravar o firmware UiFlow2 nas placas M5 |

### 3.1 Python + mpremote

```bash
# macOS (Homebrew) — ou instale o Python de python.org
brew install python
python3 -m pip install --upgrade mpremote
mpremote --version
```

Windows: `py -m pip install mpremote`. Linux: `pipx install mpremote` (e coloque o usuário
no grupo `dialout` para acessar `/dev/ttyUSB*`/`/dev/ttyACM*`).

### 3.2 arduino-cli + core ESP32 + bibliotecas

```bash
brew install arduino-cli          # Windows: winget install ArduinoSA.CLI

arduino-cli config init           # cria ~/Library/Arduino15/arduino-cli.yaml (mac)
arduino-cli config add board_manager.additional_urls \
  https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install esp32:esp32          # (ou esp32:esp32@3.3.8 para fixar a versão)

arduino-cli lib install M5Unified             # traz o M5GFX junto
```

Confira se os FQBNs usados no projeto existem:

```bash
arduino-cli board listall esp32:esp32 | grep -iE 'XIAO_ESP32C6|stickc_plus2|capsule|stamp_s3'
```

| Placa | FQBN |
|-------|------|
| XIAO ESP32-C6 | `esp32:esp32:XIAO_ESP32C6` |
| M5StickC Plus2 / PlusSE | `esp32:esp32:m5stack_stickc_plus2` |
| M5 Capsule | `esp32:esp32:m5stack_capsule` |
| M5Stamp S3 (se um dia for em Arduino) | `esp32:esp32:m5stack_stamp_s3` |

> Atenção: o core **`esp32:esp32`** (Espressif) é o certo. O `arduino:esp32` ("Arduino ESP32
> Boards", da própria Arduino) **não** tem esses FQBNs — não use.

> Os sketches usam a API do core 3.x (`esp_now_send`, `esp_wifi_set_promiscuous` etc.).
> Com o core 2.x a compilação pode falhar.

### 3.3 Drivers USB

- ESP32-S3 e ESP32-C6 (Stamp S3, Capsule, XIAO C6) usam **USB nativo**: aparecem como
  `/dev/cu.usbmodem*` (mac) ou `COMx` (Windows), sem driver.
- O M5StickC usa um conversor USB-serial: aparece como `/dev/cu.usbserial-*`. No macOS
  recente o driver já vem no sistema; se não aparecer, instale o driver **CH9102/CH34x**
  do site da M5Stack/WCH. No Windows, o mesmo driver.

### 3.4 Firmwares das placas (uma vez por placa)

| Placa | Firmware | Como gravar |
|-------|----------|-------------|
| Capsule (robô) | **UiFlow2** | M5Burner → escolha a placa → *Burn* |
| StickC PlusSE (espião tela) | **UiFlow2** | M5Burner. Traz a pasta `m5/` usada por `espiao.py` |
| Stamp S3 (controle) | MicroPython oficial (`ESP32_GENERIC_S3`) **ou** UiFlow2 | MicroPython: `esptool.py --chip esp32s3 erase_flash` e `write_flash 0 firmware.bin` (de micropython.org/download). UiFlow2: M5Burner |
| XIAO C6 (espião monitor) | nada antes | o `arduino-cli upload` grava o firmware inteiro |

Os scripts com cifra (`*_cripto.py`) usam `cryptolib`, que existe tanto no UiFlow2 quanto
no MicroPython oficial para ESP32.

**Como saber onde gravar o `main.py`:**

```bash
mpremote connect <porta> fs ls :
# se aparecer "flash/"  -> UiFlow2: grave em :/flash/main.py
# senão                  -> MicroPython puro: grave em :main.py
```

---

## 4. VS Code

### 4.1 Extensões

| Extensão | ID | Para quê |
|----------|----|----------|
| Python | `ms-python.python` | edição dos `.py` |
| Pylance | `ms-python.vscode-pylance` | análise (desligada em `micropython/`, ver abaixo) |
| C/C++ | `ms-vscode.cpptools` | edição dos `.ino` (IntelliSense básico) |
| PDF viewer (opcional) | `tomoki1207.pdf` | abrir o guia de estudo no editor |
| Arduino (opcional) | `vscode-arduino.vscode-arduino-community` | botões de compilar/gravar na barra; as *tasks* abaixo já resolvem sem ela |

Para o VS Code sugerir essas extensões a quem abrir o projeto, crie
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

### 4.2 `.vscode/settings.json` (já existe no repositório)

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

- `python.analysis.exclude`: o Pylance não conhece `network`, `espnow`, `machine`,
  `cryptolib`, `aioble`, `m5`… (só existem no firmware). Excluir a pasta evita centenas
  de avisos falsos. **É esperado.**
- `"*.ino": "cpp"` (opcional): faz o VS Code tratar o sketch como C++. Os includes do
  ESP-IDF (`esp_wifi.h`, `esp_now.h`) vão aparecer sublinhados — a compilação de verdade
  é do `arduino-cli`, então pode ignorar.

### 4.3 `.vscode/tasks.json` — gravar pelo VS Code (Ctrl/Cmd+Shift+P → *Run Task*)

Copie para `.vscode/tasks.json`. As tasks pedem a porta (e, no Arduino, o sketch e o FQBN)
a cada execução.

```json
{
  "version": "2.0.0",
  "inputs": [
    { "id": "porta", "type": "promptString",
      "description": "Porta serial (ex.: /dev/cu.usbmodem101, COM5)" },
    { "id": "sketch", "type": "pickString", "description": "Sketch Arduino",
      "options": [
        "arduino/espiao_monitor_xiao",
        "arduino/espiao_monitor_xiao_cif",
        "arduino/espiao_monitor_capsule",
        "arduino/espiao_monitor"
      ] },
    { "id": "fqbn", "type": "pickString", "description": "Placa (FQBN)",
      "options": [
        "esp32:esp32:XIAO_ESP32C6",
        "esp32:esp32:m5stack_capsule",
        "esp32:esp32:m5stack_stickc_plus2"
      ] },
    { "id": "destino", "type": "pickString", "description": "Destino do main.py",
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

> **Uma porta = um programa.** Feche o terminal com `monitor`/`repl` (ou o Thonny/Arduino IDE)
> antes de gravar, senão aparece `could not enter raw repl` ou `port busy`.

### 4.4 IntelliSense dos `.ino` (opcional)

O `arduino-cli` gera o banco de compilação, que a extensão C/C++ lê:

```bash
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32C6 \
  --only-compilation-database --build-path build/xiao arduino/espiao_monitor_xiao
```

Depois, em `.vscode/c_cpp_properties.json`:

```json
{
  "configurations": [
    { "name": "ESP32 (arduino-cli)",
      "compileCommands": "${workspaceFolder}/build/xiao/compile_commands.json" }
  ],
  "version": 4
}
```

Coloque `build/` no `.gitignore`.

---

## 5. Descrição dos arquivos

### 5.1 `micropython/` — roda nas placas MicroPython

| Arquivo | Placa | O que faz | Depende de |
|---------|-------|-----------|------------|
| [controle/controle.py](micropython/controle/controle.py) | Stamp S3 | botões → `F`/`T`/`P` em **broadcast**, texto claro; LED RGB mostra o comando | `PINO_FRENTE`, `PINO_TRAS`, `ATIVO_EM` |
| [controle/controle_unicast.py](micropython/controle/controle_unicast.py) | Stamp S3 | igual, mas **unicast** para `ROBO_MAC` | `ROBO_MAC` |
| [controle/controle_cripto.py](micropython/controle/controle_cripto.py) | Stamp S3 | cifra AES-128 (ECB, byte 0 = comando + 15 aleatórios) e envia unicast | `ROBO_MAC`, `CHAVE`, `cryptolib` |
| [espiao/espiao.py](micropython/espiao/espiao.py) | StickC PlusSE | escuta broadcast, mostra histórico na tela; A = replay, B = seleção. **Não alterar** | pasta `m5/` da placa |
| [espiao/espiao_cripto.py](micropython/espiao/espiao_cripto.py) | StickC PlusSE | mostra a cifra em hex e repete; só vê broadcast | pasta `m5/` da placa |
| [robo/robo.py](micropython/robo/robo.py) | Capsule | recebe `F/T/E/D/P` de qualquer um e chama `run_tank()` no motor | `lego_motor.py`, `aioble`, `CARD_SERIAL` |
| [robo/robo_cripto.py](micropython/robo/robo_cripto.py) | Capsule | decifra o bloco AES e move | idem + `CHAVE`, `cryptolib` |
| [robo/lego_motor.py](micropython/robo/lego_motor.py) | Capsule | driver BLE do motor LEGO Education (scan pelo Connection Card, RPC) | `aioble`, `bluetooth` |
| [ferramentas/descobre_pinos.py](micropython/ferramentas/descobre_pinos.py) | Stamp S3 | imprime qual GPIO muda ao apertar cada botão | — |
| [ferramentas/mostra_mac.py](micropython/ferramentas/mostra_mac.py) | robô | imprime `ROBO_MAC = b'...'` pronto para colar | — |
| [ferramentas/teste_motor.py](micropython/ferramentas/teste_motor.py) | robô | gira o motor por 1 s (testa só o BLE) | `lego_motor.py`, `aioble` |

**Bibliotecas MicroPython:** todas vêm no firmware (`network`, `espnow`, `machine`,
`time`, `os`, `uasyncio`, `bluetooth`, `cryptolib`), exceto:

- **`aioble`** — instalar no robô: `mpremote connect <porta> mip install --target=/flash/libs aioble`;
- **`m5`** (`m5_display`) — vem com o UiFlow2 do StickC. **Não está no repositório.** Faça backup:
  `mpremote connect <porta-espiao> fs cp -r :m5 micropython/espiao/`.

### 5.2 `arduino/` — espião em modo monitor (só existe em C)

O MicroPython não expõe `esp_wifi_set_promiscuous`; por isso este nó é Arduino.

| Sketch | Placa / FQBN | Saída | Bibliotecas |
|--------|--------------|-------|-------------|
| [espiao_monitor/](arduino/espiao_monitor/espiao_monitor.ino) | StickC Plus2/PlusSE — `esp32:esp32:m5stack_stickc_plus2` | tela: histórico; A = replay, B = seleção | M5Unified |
| [espiao_monitor_capsule/](arduino/espiao_monitor_capsule/espiao_monitor_capsule.ino) | Capsule — `esp32:esp32:m5stack_capsule` | LED RGB (GPIO21) + Serial; botão = replay | M5Unified |
| [espiao_monitor_xiao/](arduino/espiao_monitor_xiao/espiao_monitor_xiao.ino) | XIAO C6 — `esp32:esp32:XIAO_ESP32C6` | Serial + LED; BOOT repete o último **movimento**. **Falha na cifra** (didático) | só o core |
| [espiao_monitor_xiao_cif/](arduino/espiao_monitor_xiao_cif/espiao_monitor_xiao_cif.ino) | XIAO C6 — `esp32:esp32:XIAO_ESP32C6` | Serial + LED; BOOT toque = replay **verbatim**, segurar = frame anterior. Funciona na cifra | só o core |

Todos incluem `WiFi.h`, `esp_wifi.h`, `esp_now.h` (do core esp32) e têm no topo
`CANAL = 1` e `ROBO_MAC[6]` para preencher.

> Regra do Arduino: a pasta e o `.ino` têm o **mesmo nome**. Por isso cada sketch tem a sua pasta.

### 5.3 Outros

| Caminho | O que é |
|---------|---------|
| [README.md](README.md) | visão geral, demonstração e progressão pedagógica |
| [CLAUDE.md](CLAUDE.md) | convenções do projeto (canal, comandos, estrutura) |
| [arduino/README.md](arduino/README.md) | detalhes do modo monitor e roteiros de aula A e B |
| [docs/guia-de-estudo.html](docs/guia-de-estudo.html) → `.pdf` | guia de estudo (fonte HTML, PDF gerado pelo Chrome) |
| [legado/](legado/) | projetos antigos; não é necessário para o sistema atual |
| [.vscode/settings.json](.vscode/settings.json) | exclui `micropython/` e `legado/` do Pylance |

---

## 6. Convenções que precisam bater entre as placas

| Item | Valor | Onde |
|------|-------|------|
| Canal Wi-Fi/ESP-NOW | `CANAL = 1` | todos os `.py` e `.ino` |
| Broadcast | `b'\xff' * 6` / `{0xFF,…}` | controle, espiões |
| Comandos | `F` frente, `T` trás, `E` esquerda, `D` direita, `P` parar | todos |
| Rádio | `sta.config(pm=sta.PM_NONE)` e `e.config(rxbuf=2048)` antes de `e.active(True)` | MicroPython |
| MAC do robô | `ROBO_MAC` | `controle_unicast.py`, `controle_cripto.py`, todos os `.ino` |
| Chave AES (16 bytes) | `CHAVE = b"ciberseg-aes-key"` | `controle_cripto.py` **e** `robo_cripto.py` (idênticas) |
| Connection Card | `CARD_SERIAL = "7551"` | `robo.py`, `robo_cripto.py`, `teste_motor.py` |

---

## 7. Passo a passo para colocar tudo funcionando

Abra a pasta no VS Code e use o terminal integrado (`` Ctrl+` ``) na raiz do projeto.

### 7.0 Descobrir as portas

```bash
mpremote connect list
arduino-cli board list
# qual placa MicroPython está em cada porta:
for p in /dev/cu.usbmodem* /dev/cu.usbserial*; do printf "%s: " $p; \
  mpremote connect $p exec "import sys;print(sys.implementation._machine)"; done
```

Plugue **uma placa de cada vez** na primeira vez e anote a porta de cada uma.

### 7.1 Robô (Capsule, UiFlow2)

```bash
mpremote connect <porta-robo> run micropython/ferramentas/mostra_mac.py   # anote o ROBO_MAC
mpremote connect <porta-robo> mip install --target=/flash/libs aioble
mpremote connect <porta-robo> fs cp micropython/robo/lego_motor.py :/flash/lego_motor.py
# teste isolado do motor (motor ligado, FORA do carregador):
mpremote connect <porta-robo> run micropython/ferramentas/teste_motor.py
# grava o programa do robô:
mpremote connect <porta-robo> fs cp micropython/robo/robo.py :/flash/main.py + reset
```

Antes, ajuste `CARD_SERIAL` em `robo.py`. Se uma roda girar ao contrário: `INVERTER_ESQUERDO` / `INVERTER_DIREITO`.

### 7.2 Controle (Stamp S3)

```bash
mpremote connect <porta-controle> run micropython/ferramentas/descobre_pinos.py
```

Aperte cada botão, preencha `PINO_FRENTE`, `PINO_TRAS` e `ATIVO_EM` (`1 -> 0` ⇒ `ATIVO_EM = 0`;
`0 -> 1` ⇒ `ATIVO_EM = 1`) em `controle.py` (e nas versões unicast/cripto). Depois:

```bash
mpremote connect <porta-controle> fs cp micropython/controle/controle.py :main.py + reset
```

(Use `:/flash/main.py` se o Stamp estiver com UiFlow2.)

### 7.3 Espião com tela (StickC PlusSE, UiFlow2)

```bash
mpremote connect <porta-espiao> fs cp -r :m5 micropython/espiao/     # backup, uma vez
mpremote connect <porta-espiao> fs cp micropython/espiao/espiao.py :main.py + reset
```

### 7.4 Espião em modo monitor (XIAO ESP32-C6, Arduino)

1. Cole o `ROBO_MAC` do passo 7.1 em `ROBO_MAC[6]` no topo do `.ino`
   (ex.: `{ 0x48, 0x27, 0xe2, 0xe3, 0xac, 0x78 }`).
2. Compile e grave:

```bash
arduino-cli compile --upload -p <porta-xiao> --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao
arduino-cli monitor  -p <porta-xiao> -c baudrate=115200
```

Para a versão que repete a cifra, troque só a pasta: `arduino/espiao_monitor_xiao_cif`.

Para a StickC ou a Capsule, troque FQBN e pasta (ver tabela 5.2). Gravar um sketch
Arduino **apaga o MicroPython** da placa; para voltar, regrave o UiFlow2 pelo M5Burner.

### 7.5 Trocar de etapa da aula

| Etapa | Controle | Robô | Espião que captura |
|-------|----------|------|---------------------|
| 1. Broadcast em claro | `controle.py` | `robo.py` | `espiao.py` (StickC) e o monitor |
| 2. Unicast em claro | `controle_unicast.py` | `robo.py` | só o monitor (`espiao_monitor_xiao`) |
| 3. Unicast cifrado | `controle_cripto.py` | `robo_cripto.py` | monitor `espiao_monitor_xiao` **falha**; `espiao_monitor_xiao_cif` **repete** |

```bash
mpremote connect <porta-controle> fs cp micropython/controle/controle_cripto.py :main.py + reset
mpremote connect <porta-robo>     fs cp micropython/robo/robo_cripto.py       :/flash/main.py + reset
```

Para voltar ao claro, regrave `controle.py` (ou `controle_unicast.py`) e `robo.py`.

### 7.6 Demonstração

1. Ligue o motor LEGO (fora do carregador) e o robô; espere a conexão BLE.
2. Ligue os espiões (tela: `ESPIAO ... ouvindo`; XIAO: abra o monitor serial).
3. Aperte FRENTE no controle: o robô anda e o espião registra.
4. Solte. No espião, selecione o `FRENTE` capturado e faça o replay: **o robô anda sozinho**.

---

## 8. Problemas comuns

| Sintoma | Causa / solução |
|---------|-----------------|
| `could not enter raw repl` / `port busy` | porta ocupada: feche `monitor`, `repl`, Thonny, Arduino IDE |
| Upload do XIAO para em `Connecting...` | segure **BOOT**, aperte **RESET**, solte **BOOT**, rode o upload de novo |
| XIAO gravado mas a serial não mostra nada | aperte RESET com o monitor aberto; se continuar mudo, grave com `--board-options CDCOnBoot=cdc` |
| Robô não acha o motor | `CARD_SERIAL` errado (a falha mais comum) ou motor no carregador |
| Erro de versão RPC no motor | atualize o firmware em code.legoeducation.com |
| `ImportError: aioble` | faltou o `mip install --target=/flash/libs aioble` no robô |
| `ImportError: m5` no espião | a placa não tem UiFlow2 ou a pasta `m5/` foi apagada: regrave o UiFlow2 |
| Nada acontece após `fs cp` | gravou no lugar errado (`:main.py` × `:/flash/main.py`) ou faltou `+ reset` |
| Controle/espião em unicast não veem nada | esperado: só o espião em **modo monitor** vê unicast |
| Robô não obedece ao controle cifrado | `CHAVE` diferente entre controle e robô, ou `ROBO_MAC` errado |
| `arduino-cli`: FQBN desconhecido | core errado: instale `esp32:esp32` (Espressif) com a URL do item 3.2 |
| Pylance cheio de avisos em `micropython/` | falta o `python.analysis.exclude` do `.vscode/settings.json` |
| Placa não aparece na lista de portas | cabo só de carga, ou driver CH9102/CH34x (StickC) ausente |
| Controle trava ao usar GPIO19/20 | são o USB do Stamp S3: escolha outros pinos |

---

## 9. Checklist rápido de um computador novo

- [ ] Python 3 + `pip install mpremote`
- [ ] `arduino-cli` + URL do Espressif + `core install esp32:esp32` + `lib install M5Unified`
- [ ] VS Code + extensões Python, Pylance, C/C++
- [ ] `.vscode/` já vem pronto no repo (`settings.json`, `tasks.json`, `extensions.json`, `c_cpp_properties.json`)
- [ ] Rodar a task **Arduino: gerar IntelliSense (XIAO)** uma vez (cria `build/xiao/compile_commands.json`)
- [ ] M5Burner com UiFlow2 no Capsule e no StickC; MicroPython ou UiFlow2 no Stamp S3
- [ ] `aioble` + `lego_motor.py` no robô; backup da pasta `m5/` do espião
- [ ] `ROBO_MAC`, `CARD_SERIAL`, `PINO_FRENTE`/`PINO_TRAS`/`ATIVO_EM`, `CHAVE` conferidos
- [ ] Cabos USB de dados e power banks
