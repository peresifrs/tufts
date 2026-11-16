# arduino/ — nós que precisam de C (ESP-IDF via Arduino)

Pasta irmã de `micropython/`, para o que o firmware MicroPython não entrega.
Hoje só o **espião em modo monitor**, porque promíscuo/monitor não existe na
API MicroPython (UiFlow2) — só em C (`esp_wifi_set_promiscuous`).

```
arduino/
├── espiao_monitor/espiao_monitor.ino                  # COM TELA (M5StickC PlusSE etc.)
├── espiao_monitor_capsule/espiao_monitor_capsule.ino  # M5 Capsule: LED RGB + Serial
├── espiao_monitor_xiao/espiao_monitor_xiao.ino        # XIAO: LÊ o comando (falha na cifra)
├── espiao_monitor_xiao_cif/espiao_monitor_xiao_cif.ino # XIAO: REPETE verbatim (serve na cifra)
└── espiao_monitor_xiao_term/espiao_monitor_xiao_term.ino # XIAO: terminal, escolhe o replay (versão 2)
```

> **As duas versões do XIAO são propositais (didático).** `espiao_monitor_xiao`
> só repete o que reconhece (F/T/E/D) — mostre-o **falhando** contra a cifra
> (`nenhum movimento capturado`). Depois grave `espiao_monitor_xiao_cif`, que
> repete os bytes **verbatim** e faz o robô obedecer mesmo sem entender o comando.

## Arranjo recomendado: um nó por placa, sem regravar firmware

O espião MicroPython com tela (`micropython/espiao/espiao.py`, broadcast) fica
**intacto** na sua placa com display. O sniffer em modo monitor vai numa placa
**separada** (uma M5 Capsule), rodando o firmware Arduino. Assim você não regrava
firmware de ida e volta: na demonstração, os dois espiões coexistem e mostram a
diferença — o broadcast cega com o unicast, o monitor continua capturando.

| Sketch | Placa | FQBN | Saída |
|--------|-------|------|-------|
| `espiao_monitor` | StickC PlusSE / Plus2 (com tela) | `esp32:esp32:m5stack_stickc_plus2` | tela (histórico + replay por botão) |
| `espiao_monitor_capsule` | M5 Capsule (sem tela) | `esp32:esp32:m5stack_capsule` | LED RGB (cor = último comando) + Serial; botão = replay do último |
| `espiao_monitor_xiao` | XIAO ESP32-C6 (sem tela) | `esp32:esp32:XIAO_ESP32C6` | Serial + LED; BOOT = replay do último **movimento** (F/T/E/D). Texto claro; **falha na cifra** (didático) |
| `espiao_monitor_xiao_cif` | XIAO ESP32-C6 (sem tela) | `esp32:esp32:XIAO_ESP32C6` | Serial + LED; BOOT: toque = replay do selecionado, segurar = frame anterior. Repete **verbatim** (funciona na cifra) |
| `espiao_monitor_xiao_term` | XIAO ESP32-C6 (sem tela) | `esp32:esp32:XIAO_ESP32C6` | **Controle pelo terminal**: histórico numerado (BCAST/UNI, MAC, RSSI, hex) e `<n>` repete o pacote n (verbatim; serve em claro, unicast e cifra). `l` lista, `u` último, `7 x3` repete 3×, `m` pausa ao vivo, `c` limpa |

> **Gravar o XIAO é o caminho mais fácil.** BOOT/RESET acessíveis e auto-reset
> costuma funcionar. Se o upload travar no "Connecting...": segure **BOOT**,
> aperte **RESET**, solte **BOOT**, e rode o upload.

## Por que este nó é C e os outros são MicroPython

Quando o controle passa a enviar **unicast** (`controle_unicast.py`), o rádio de
um espião ESP-NOW comum descarta tudo que não é endereçado ao MAC dele: a tela
fica vazia. O modo monitor lê **todo** frame 802.11 do canal, inclusive o unicast
destinado ao robô — e aí o replay volta a funcionar. Lição: endereçar ≠ cifrar.

`controle_unicast.py` e `robo.py` continuam em MicroPython; o robô **não muda**
(em ESP-NOW só é preciso registrar peer para *enviar*, não para *receber*).

## Pré-requisitos

- **Arduino IDE** (ou PlatformIO) com o core **esp32 by Espressif**.
- Biblioteca **M5Unified** (Gerenciador de Bibliotecas). Ela detecta o PlusSE em runtime.

## Antes de gravar: preencha o MAC do robô

O sketch precisa do MAC do robô (destino do unicast e do replay). Descubra com:

```bash
mpremote connect <porta-robo> run micropython/ferramentas/mostra_mac.py
```

Copie os 6 bytes para `ROBO_MAC[6]` no topo de
[espiao_monitor.ino](espiao_monitor/espiao_monitor.ino), por exemplo:

```c
static uint8_t ROBO_MAC[6] = { 0x24, 0x6f, 0x28, 0xaa, 0xbb, 0xcc };
```

## Gravar

1. Arduino IDE → selecione uma placa M5Stack ESP32 (ex.: **M5StickCPlus2**).
2. Selecione a porta serial do espião (ex.: `/dev/cu.usbserial-7D5A347739`).
3. **Fechar qualquer `mpremote`/monitor** nessa porta antes (uma porta = um programa).
4. Upload.

> Isto **substitui** o MicroPython da placa espião por um firmware Arduino.
> O `espiao.py` (broadcast) e a pasta `m5/` deixam de ser usados enquanto este
> sketch estiver gravado. Para voltar ao espião MicroPython, regrave o firmware
> UiFlow2 e recopie `espiao.py`. Faça backup da pasta `m5/` antes (veja o
> cabeçalho de `micropython/espiao/espiao.py`).

### Gravar por linha de comando (arduino-cli)

Core esp32 e lib M5Unified instalados uma vez:
```bash
arduino-cli core install esp32:esp32
arduino-cli lib install M5Unified          # só para as variantes com M5 (tela/Capsule)
```
Compilar e gravar (troque o FQBN/pasta conforme a placa — ver tabela acima):
```bash
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao
arduino-cli upload  -p <porta> --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao
```

## Ver a saída serial (115200 baud)

As variantes sem tela (Capsule, XIAO) mostram as capturas pela **serial** — é a
saída boa para projetar na aula. Com o sketch já gravado e rodando:

```bash
arduino-cli monitor -p <porta> -c baudrate=115200
```

Alternativas: Monitor Serial da Arduino IDE a **115200**, ou `screen <porta> 115200`
(sai com `Ctrl-A` depois `K`). Lembre: **uma porta = um programa** — feche o monitor
antes de regravar. Você verá linhas como:

```
[3] capturou FRENTE de ac:a7:04:03:45:70
REPLAY -> FRENTE (ok)
```

## Roteiros de aula

### A) Unicast: o espião comum fica cego, o monitor não

1. Controle rodando `controle_unicast.py`, robô rodando `robo.py`.
2. Mostre que um espião ESP-NOW comum (o `espiao.py` antigo) **não vê mais** o unicast.
3. No XIAO C6 com `espiao_monitor_xiao_term`, abra o terminal (tarefa **Espião XIAO:
   terminal** no VS Code, ou `arduino-cli monitor -p <porta-xiao> -c baudrate=115200`).
   Aperte e solte FRENTE: aparecem `#1 ... UNI ... FRENTE 46` e `#2 ... UNI ... PARAR 50`.
4. Digite `1` + Enter: `REPLAY #1 -> robo FRENTE (ok)` e o robô anda. `l` lista,
   `1 x3` repete 3×, `u` repete o último, `m` pausa a impressão ao vivo.

### B) Cifra: repetir sem entender (versão 3, padrão)

Controle com `controle_cripto.py`, robô com `robo_cripto.py`, XIAO **continua** com
`espiao_monitor_xiao_term` (não regrava). No terminal os pacotes aparecem como
`#1 ... UNI ... 16B  ? (ilegivel)  3fa1c9...`. Digite `1` + Enter: o robô anda.
O espião não sabe o comando, mas repete os bytes e o robô decifra e obedece.

### B') Alternativa: o espião que lê falha, o que repete funciona

Pré: controle com `controle_cripto.py` (cifra + **unicast** para `ROBO_MAC`) e robô com
`robo_cripto.py` (mesma `CHAVE`). O tráfego é unicast: o espião MicroPython não vê nada,
só o modo monitor captura.
Use o XIAO C6 como espião e mostre a diferença entre as duas versões.

**Passo 1 — o espião que LÊ o comando falha na cifra.** Grave a versão antiga:
```bash
arduino-cli upload -p <porta-xiao> --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao
arduino-cli monitor -p <porta-xiao> -c baudrate=115200
```
Aperte FRENTE no controle. A serial mostra `capturou ? de ...` (não lê o comando) e,
ao apertar BOOT, `replay: nenhum movimento capturado`. **Ele vê, mas não sabe repetir.**
Pergunte à turma: por quê? (a cifra escondeu qual byte é o comando.)

**Passo 2 — o espião que REPETE verbatim funciona mesmo cifrado.** Grave a versão `_cif`:
```bash
arduino-cli upload -p <porta-xiao> --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao_cif
arduino-cli monitor -p <porta-xiao> -c baudrate=115200
```
Aperte FRENTE e solte (o XIAO captura a cifra do `F` e depois a do `P`). No XIAO:
**segure BOOT** (seleciona o frame anterior = o `F` cifrado) e **solte**; depois **toque
BOOT** → o robô **anda sozinho**. A serial mostra `REPLAY [n] <hex> -> ok`.
**Repetir não exige entender** — cifra dá confidencialidade, não autenticidade.

> As duas versões usam o mesmo FQBN e placa: para alternar, troque só a **pasta**
> no comando de upload (`espiao_monitor_xiao` ↔ `espiao_monitor_xiao_cif`).
> Uma porta = um programa: feche o `monitor` antes de regravar.
