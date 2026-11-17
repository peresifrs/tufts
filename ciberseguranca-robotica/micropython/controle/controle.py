# controle.py - CONTROLE de botoes (M5Stamp S3 + Breakout v2), sem PC.
#
# Dois botoes ligados na shield breakout:
#   botao FRENTE -> enquanto apertado o robo anda para frente  (envia "F")
#   botao TRAS   -> enquanto apertado o robo anda para tras    (envia "T")
#   soltou       -> o robo para                                (envia "P")
#
# Os comandos vao por ESP-NOW em BROADCAST e em texto claro: o robo obedece e o
# ESPIAO (M5 com tela) tambem ouve tudo e pode repetir (replay). E de proposito.
#
# Grave na placa como main.py (inicia sozinho ao ligar, roda na power bank):
#   mpremote connect <porta-controle> fs cp micropython/controle/controle.py :main.py
#   (firmware UiFlow2: use :/flash/main.py)
#
# NAO sabe em que GPIO estao os botoes? Rode antes ferramentas/descobre_pinos.py.

import network
import espnow
import time
from machine import Pin

# ====================== CONFIGURACAO ======================
CANAL = 1                 # mesmo canal de todas as placas
BROADCAST = b'\xff' * 6

# GPIO de cada botao na Breakout v2. CONFIRA com ferramentas/descobre_pinos.py.
# Vem como None de proposito: o programa avisa e para ate voce preencher.
PINO_FRENTE = 4
PINO_TRAS = 1

# Botao ligado entre o GPIO e o GND -> ATIVO_EM = 0 (usa pull-up interno).
# Botao ligado entre o GPIO e o 3V3 -> ATIVO_EM = 1 (usa pull-down interno).
ATIVO_EM = 0

PINO_LED = 21             # LED RGB (WS2812) do Stamp S3; None desliga o feedback
# ==========================================================

if PINO_FRENTE is None or PINO_TRAS is None:
    raise SystemExit("Fill in PINO_FRENTE and PINO_TRAS at the top of controle.py "
                     "(use ferramentas/descobre_pinos.py to find them).")

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
e.add_peer(BROADCAST)

print("=" * 40)
print("Role  : controller (buttons)")
print("MAC   :", mac_str(sta.config('mac')))
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
        e.send(BROADCAST, cmd.encode())
    except OSError as erro:
        print("send failed", cmd, erro)
        return
    seq += 1
    print("[%d] sent: %s" % (seq, cmd))
    led(cmd)

def comando_atual():
    f, t = apertado(btn_frente), apertado(btn_tras)
    if f and not t:
        return "F"
    if t and not f:
        return "T"
    return "P"            # nenhum (ou os dois) apertado = parar

# ---------- Laco principal ----------
# So envia quando o estado MUDA: o espiao ve um comando por apertada,
# o que deixa o historico dele limpo para a demonstracao do replay.
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
