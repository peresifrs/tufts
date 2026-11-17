# controle_unicast.py - CONTROLE de botoes enviando por ESP-NOW UNICAST, sem PC.
#
# Igual ao controle.py, SO MUDA O DESTINO: em vez de BROADCAST (b'\xff'*6),
# os comandos vao enderecados ao MAC do robo (ROBO_MAC). Assim:
#   - o robo continua recebendo e obedecendo (F/T/P);
#   - um espiao em ESP-NOW "normal" NAO ve mais nada: o radio dele descarta
#     frames que nao sao para o MAC dele. A confidencialidade parece resolvida...
#   - ...mas um sniffer em MODO MONITOR (promiscuo) le o ar inteiro e captura o
#     unicast mesmo assim. Essa e a licao: endereçar != cifrar.
#
# Grave na placa como main.py (firmware UiFlow2: use :/flash/main.py):
#   mpremote connect <porta-controle> fs cp micropython/controle/controle_unicast.py :main.py
#
# ANTES: descubra o MAC do robo e preencha ROBO_MAC abaixo:
#   mpremote connect <porta-robo> run micropython/ferramentas/mostra_mac.py

import network
import espnow
import time
from machine import Pin

# ====================== CONFIGURACAO ======================
CANAL = 1                 # mesmo canal de todas as placas

# MAC do ROBO (destino do unicast). Descubra com ferramentas/mostra_mac.py.
# Vem None de proposito: o programa avisa e para ate voce preencher.
ROBO_MAC = b'\xa0\xf2\x62\x87\xaf\x74'   # descoberto com ferramentas/mostra_mac.py

# GPIO de cada botao na Breakout v2 (iguais ao controle.py).
PINO_FRENTE = 4
PINO_TRAS = 1

# Botao ligado entre o GPIO e o GND -> ATIVO_EM = 0 (usa pull-up interno).
# Botao ligado entre o GPIO e o 3V3 -> ATIVO_EM = 1 (usa pull-down interno).
ATIVO_EM = 0

PINO_LED = 21             # LED RGB (WS2812) do Stamp S3; None desliga o feedback
# ==========================================================

if ROBO_MAC is None:
    raise SystemExit("Fill in ROBO_MAC at the top of controle_unicast.py "
                     "(use ferramentas/mostra_mac.py on the robot to find it).")
if PINO_FRENTE is None or PINO_TRAS is None:
    raise SystemExit("Fill in PINO_FRENTE and PINO_TRAS at the top of controle_unicast.py.")

# ---------- Radio ESP-NOW ----------
def mac_str(b):
    return ':'.join('%02x' % x for x in b)

sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.disconnect()              # ESP-NOW nao precisa de rede WiFi
sta.config(channel=CANAL)
sta.config(pm=sta.PM_NONE)

e = espnow.ESPNow()
e.config(rxbuf=2048)
e.active(True)
e.add_peer(ROBO_MAC)          # unicast: precisa registrar o destino para enviar

print("=" * 40)
print("Role  : UNICAST controller (buttons)")
print("MAC   :", mac_str(sta.config('mac')))
print("Dest  :", mac_str(ROBO_MAC))
print("Chan  :", sta.config('channel'), "(expected %d)" % CANAL)
print("Btns  : FWD=GPIO%d  BACK=GPIO%d" % (PINO_FRENTE, PINO_TRAS))
print("=" * 40)

# ---------- Botoes ----------
_pull = Pin.PULL_UP if ATIVO_EM == 0 else Pin.PULL_DOWN
btn_frente = Pin(PINO_FRENTE, Pin.IN, _pull)
btn_tras = Pin(PINO_TRAS, Pin.IN, _pull)

def apertado(pin):
    return pin.value() == ATIVO_EM

# ---------- LED de feedback (opcional: nunca derruba o programa) ----------
_led = None
if PINO_LED is not None:
    try:
        import neopixel
        _led = neopixel.NeoPixel(Pin(PINO_LED, Pin.OUT), 1)
    except Exception:
        _led = None

CORES = {"F": (0, 40, 0), "T": (40, 0, 0), "P": (0, 0, 8)}   # verde, vermelho, azul fraco

def led(cmd):
    if _led is None:
        return
    try:
        _led[0] = CORES.get(cmd, (0, 0, 0))
        _led.write()
    except Exception:
        pass

# ---------- Envio ----------
seq = 0

def enviar(cmd):
    global seq
    try:
        e.send(ROBO_MAC, cmd.encode())
    except OSError as erro:
        print("send failed", cmd, erro)
        return
    seq += 1
    print("[%d] sent (unicast): %s" % (seq, cmd))
    led(cmd)

def comando_atual():
    f, t = apertado(btn_frente), apertado(btn_tras)
    if f and not t:
        return "F"
    if t and not f:
        return "T"
    return "P"            # nenhum (ou os dois) apertado = parar

# ---------- Laco principal ----------
# So envia quando o estado MUDA (igual ao controle.py).
ultimo = "P"
led(ultimo)
while True:
    cmd = comando_atual()
    if cmd != ultimo:
        time.sleep_ms(20)              # debounce: confirma depois de 20 ms
        if comando_atual() == cmd:
            enviar(cmd)
            ultimo = cmd
    time.sleep_ms(10)
