# ciberseg-esp32

Cibersegurança com robótica para a educação básica (IFRS/POALab + Tufts/CEEO).
Três ESP32 conversam por **ESP-NOW em broadcast e texto claro** — de propósito
inseguro — e um motor LEGO Education é o "robô". **Nada depende do computador**:
cada placa roda sozinha numa bateria/power bank. O PC só serve para gravar.

```
 [CONTROLE]  --ESP-NOW broadcast-->  [ROBO]  --BLE-->  [motor LEGO]
  Stamp S3          "F" / "T" / "P"    Capsule
  2 botoes                 |
                           v  (todo mundo ouve)
                       [ESPIAO]  M5StickC PlusSE com tela
                       ve os comandos e faz REPLAY -> o robo obedece
```

**A lição:** o espião **lê** tudo (confidencialidade quebrada) e, ao repetir um
comando capturado, o robô **obedece ao impostor** (autenticidade quebrada) — ele não
tem como saber quem mandou.

> **Guia de estudo completo** (conceitos, os três modelos, os modos do espião, código
> comentado e roteiro de aula): [docs/guia-de-estudo-ciberseg-esp32.pdf](docs/guia-de-estudo-ciberseg-esp32.pdf).
> A fonte é [docs/guia-de-estudo.html](docs/guia-de-estudo.html). Para regerar o PDF depois de editar:
> `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --no-pdf-header-footer --print-to-pdf=docs/guia-de-estudo-ciberseg-esp32.pdf docs/guia-de-estudo.html`

## As três placas

| Nó | Placa | Pasta | O que faz |
|----|-------|-------|-----------|
| **Controle** | M5Stamp S3 + Breakout v2 | [micropython/controle/](micropython/controle/) | botão FRENTE envia `F`, botão TRÁS envia `T`, soltar envia `P` |
| **Espião** | M5StickC PlusSE (tela) | [micropython/espiao/](micropython/espiao/) | mostra o que foi capturado; botão A = replay, botão B = escolhe no histórico |
| **Robô** | M5Stack Capsule | [micropython/robo/](micropython/robo/) | recebe o comando e move o motor LEGO por BLE |

Os códigos são MicroPython e rodam iguais em M5 e em XIAO ESP32-C6. Só mudam os
pinos e o caminho do filesystem.

## Gravar (uma vez por placa)

```bash
cd ~/Documents/ifrs/VSCode/ciberseg-esp32
mpremote connect list                  # descubra a porta de cada placa
```

> **Firmware UiFlow2** (M5 com `/flash`): grave em `:/flash/main.py`.
> **MicroPython puro**: grave em `:main.py`. Na dúvida: `mpremote connect <porta> fs ls :`.

### Robô (Capsule)
```bash
mpremote connect <porta-robo> mip install --target=/flash/libs aioble
mpremote connect <porta-robo> fs cp micropython/robo/lego_motor.py :/flash/lego_motor.py
mpremote connect <porta-robo> fs cp micropython/robo/robo.py :/flash/main.py
```
Ajuste `CARD_SERIAL` em `robo.py` para o número do Connection Card (padrão `7551`).
Se uma roda girar ao contrário, use `INVERTER_ESQUERDO` / `INVERTER_DIREITO`.

### Espião (M5StickC PlusSE)
```bash
mpremote connect <porta-espiao> fs cp micropython/espiao/espiao.py :main.py
```
A pasta `m5/` (driver da tela) **já está na placa e não está no repositório**. Faça
backup uma vez: `mpremote connect <porta-espiao> fs cp -r :m5 micropython/espiao/`.

### Controle (Stamp S3 + Breakout v2)
1. Descubra os GPIOs dos botões:
   ```bash
   mpremote connect <porta-controle> run micropython/ferramentas/descobre_pinos.py
   ```
   Aperte cada botão e anote o GPIO que aparece.
2. Preencha `PINO_FRENTE` e `PINO_TRAS` no topo de `micropython/controle/controle.py`.
   Se aparecer `1 -> 0`, mantenha `ATIVO_EM = 0`. Se aparecer `0 -> 1`, mude para `ATIVO_EM = 1`.
3. Grave:
   ```bash
   mpremote connect <porta-controle> fs cp micropython/controle/controle.py :main.py
   ```
O LED RGB do Stamp mostra o comando: verde = frente, vermelho = trás, azul = parado.

## Demonstração
1. Ligue o motor LEGO (fora do carregador) e o robô. Espere a conexão BLE.
2. Ligue o espião. A tela mostra `ESPIAO ... ouvindo`.
3. Ligue o controle. Aperte FRENTE: o robô anda e o espião mostra `FRENTE`.
4. Solte e veja o robô parar. No espião, selecione `FRENTE` com B e aperte A: **o robô anda sozinho**.

## Duas versões do controle: broadcast e unicast

Há duas versões do **controle**, para contrastar "todo mundo ouve" com
"endereçado a um só". O **robô não muda** entre elas (recebe de qualquer
remetente); só o controle troca.

| Versão | Arquivo | Como envia | Espião broadcast (StickC) | Sniffer monitor |
|--------|---------|-----------|----------------------------|-----------------|
| Broadcast | [controle.py](micropython/controle/controle.py) | para todos (`b'\xff'*6`) | **captura** | captura |
| Unicast | [controle_unicast.py](micropython/controle/controle_unicast.py) | só para o MAC do robô | **não captura** | **captura** (lê o ar) |

A versão unicast precisa do MAC do robô em `ROBO_MAC`. Descubra com:
```bash
mpremote connect <porta-robo> run micropython/ferramentas/mostra_mac.py
# cole a linha "ROBO_MAC = b'...'" no topo de controle_unicast.py
```

### Trocar a versão gravada no controle

O controle é o **AtomS3 / Stamp S3**. Como os nomes de porta trocam de papel,
confirme qual é antes de gravar:
```bash
for p in /dev/cu.usbmodem*; do printf "%s: " $p; mpremote connect $p exec "import sys;print(sys.implementation._machine)"; done
```

Broadcast:
```bash
mpremote connect <porta-controle> fs cp micropython/controle/controle.py :main.py + reset
```
Unicast:
```bash
mpremote connect <porta-controle> fs cp micropython/controle/controle_unicast.py :main.py + reset
```

> O `+ reset` reinicia a placa para rodar o novo `main.py`. Depois de um `exec`
> de diagnóstico, use `+ reset` também para a placa voltar a rodar o programa.

## Espião em modo monitor (captura o unicast)

Com o controle em unicast, o espião MicroPython broadcast para de ver o tráfego.
Um sniffer em **modo monitor (promíscuo)** lê o canal inteiro e captura o unicast
mesmo assim — e isso **só existe em C (Arduino)**, não em MicroPython (o firmware
não expõe modo monitor). Lição: endereçar ≠ cifrar.

Variantes prontas em [arduino/](arduino/) (veja [arduino/README.md](arduino/README.md)):
- `arduino/espiao_monitor/` — placa com tela (StickC), histórico + replay por botão.
- `arduino/espiao_monitor_capsule/` — M5 Capsule (LED RGB + Serial).
- `arduino/espiao_monitor_xiao/` — XIAO ESP32-C6 (Serial + LED), **a mais fácil de gravar**. Lê o comando (F/T/E/D) e repete o último movimento — **falha contra a cifra** (use para mostrar o espião sem saber repetir).
- `arduino/espiao_monitor_xiao_cif/` — mesma placa, mas repete o frame **verbatim** (toque = selecionado, segurar = anterior), então **funciona mesmo cifrado**.

Gravar com arduino-cli (exemplo XIAO C6):
```bash
arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao
arduino-cli upload -p <porta> --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao
```

Ver a saída serial (as variantes Capsule/XIAO mostram as capturas pela serial, a 115200):
```bash
arduino-cli monitor -p <porta> -c baudrate=115200
```

## Versão com criptografia (confidencialidade ≠ autenticidade)

Agora o controle **cifra** o comando (AES-128) e o envia em **unicast** para o robô,
que **decifra**. Por ser unicast, só um espião em **modo monitor** captura o tráfego:
o espião MicroPython fica cego, como no unicast em claro. O espião **não tem a chave**: não consegue ler o comando (só vê bytes embaralhados).
**Mas ainda consegue repetir** — captura a cifra e reenvia os mesmos bytes; o robô
decifra e obedece. Cifrar dá **confidencialidade, não autenticidade**. A defesa
(próxima versão) é HMAC + número de sequência/nonce contra replay.

Diferente das outras versões, aqui controle e robô são um **conjunto casado**: trocam
juntos, a `CHAVE` (16 bytes) tem de ser idêntica nos dois e o `ROBO_MAC` do controle
é o mesmo do `controle_unicast.py`:

| Nó | Arquivo |
|----|---------|
| Controle | [controle_cripto.py](micropython/controle/controle_cripto.py) (unicast para `ROBO_MAC`) |
| Robô | [robo_cripto.py](micropython/robo/robo_cripto.py) |
| Espião | [arduino/espiao_monitor_xiao_cif/](arduino/espiao_monitor_xiao_cif/) (modo monitor; repete a cifra verbatim) |

```bash
mpremote connect <porta-controle> fs cp micropython/controle/controle_cripto.py :main.py + reset
mpremote connect <porta-robo>     fs cp micropython/robo/robo_cripto.py       :/flash/main.py
arduino-cli upload -p <porta-xiao> --fqbn esp32:esp32:XIAO_ESP32C6 arduino/espiao_monitor_xiao_cif
```

> O [espiao_cripto.py](micropython/espiao/espiao_cripto.py) (StickC, mostra a cifra em hex)
> só captura cifra enviada em broadcast. Contra o controle cifrado em unicast ele fica
> em `ouvindo` — o mesmo que acontece com o `espiao.py` no unicast em claro.

> A `CHAVE` fica fixa no código só por ser didático — **não é seguro** (quem lê o
> repositório tem a chave). O ponto da aula é o replay, não a gestão de chaves.
> Para voltar ao claro, regrave `controle.py` (ou `controle_unicast.py`) e `robo.py`.

Para demonstrar isso com o espião monitor (XIAO), há duas versões propositais —
uma que lê o comando e **falha** na cifra, outra que repete **verbatim** e funciona —
com o passo a passo e os comandos de carga no **Roteiro B** de
[arduino/README.md](arduino/README.md).

## Ferramentas
- [descobre_pinos.py](micropython/ferramentas/descobre_pinos.py): mostra qual GPIO muda ao apertar um botão.
- [mostra_mac.py](micropython/ferramentas/mostra_mac.py): imprime o MAC da placa (use no robô para preencher `ROBO_MAC`).
- [teste_motor.py](micropython/ferramentas/teste_motor.py): gira o motor LEGO por 1 s, para testar o BLE isoladamente.

## Problemas comuns
- `could not enter raw repl`: a porta está ocupada (feche Thonny ou outro REPL).
- O robô não acha o motor: confira o `CARD_SERIAL`; o motor não funciona enquanto está no carregador.
- Erro de versão RPC no motor: atualize o firmware em code.legoeducation.com.
- Use cabos USB **de dados**, não os "charge-only".

## Legado
[legado/](legado/) guarda as cópias dos projetos antigos (`ciberseg-lego`, `ciberseg-m5`,
`lego-esp32-micropython`): a versão com ponte no PC, o MITM pelo teclado e as ideias de
unicast/cifrado. Nada ali é necessário para o sistema atual.
