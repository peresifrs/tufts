# controle_cripto.py - CONTROLE que CIFRA o comando e envia em UNICAST ao robo (ESP-NOW).
#
# Igual ao controle_unicast.py (destino = ROBO_MAC), mas em vez de mandar "F"/"T"/"P"
# em texto claro, manda um bloco de 16 bytes cifrado em AES. A CHAVE e a mesma do
# robo (robo_cripto.py).
#
# Bloco cifrado = AES-ECB( byte0=comando + 15 bytes ALEATORIOS ).
#   - o aleatorio faz o MESMO comando virar uma cifra diferente a cada envio,
#     entao o espiao nao le o comando nem consegue agrupar cifras iguais;
#   - MAS a cifra ainda pode ser REPETIDA (replay): sem integridade/nonce, o robo
#     aceita qualquer bloco que decifre bem. Essa e a licao desta versao.
#
# Por ser unicast, um espiao ESP-NOW comum (espiao_cripto.py) nao ve nada; so um
# sniffer em MODO MONITOR (arduino/espiao_monitor_xiao_cif) captura - e repete.
#
# Proxima versao (defesa): HMAC + numero de sequencia/nonce contra replay.
#
# Grave na placa como main.py (firmware UiFlow2: use :/flash/main.py):
#   mpremote connect <porta-controle> fs cp micropython/controle/controle_cripto.py :main.py
#
# ANTES: preencha ROBO_MAC (o mesmo do controle_unicast.py):
#   mpremote connect <porta-robo> run micropython/ferramentas/mostra_mac.py

import network
import espnow
import time
import os
from machine import Pin

try:
    import cryptolib                      # MicroPython novo
except ImportError:
    import ucryptolib as cryptolib        # firmwares antigos

# ====================== CONFIGURACAO ======================
CANAL = 1                 # mesmo canal de todas as placas

# MAC do ROBO (destino do unicast). Descubra com ferramentas/mostra_mac.py.
ROBO_MAC = b'\xa0\xf2\x62\x87\xaf\x74'

# CHAVE AES de 16 bytes. DEVE ser IDENTICA no robo_cripto.py.
# (Chave fixa no codigo e didatico, nao seguro: qualquer um que leia o repo a tem.)
CHAVE = b"ciberseg-aes-key"
MODO_ECB = 1              # cryptolib: 1 = ECB

# GPIO dos botoes (iguais ao controle.py).
PINO_FRENTE = 4
PINO_TRAS = 1
ATIVO_EM = 0              # botao no GND -> 0; botao no 3V3 -> 1

PINO_LED = 21             # LED RGB do Stamp S3; None desliga o feedback
# ==========================================================

if ROBO_MAC is None:
    raise SystemExit("Fill in ROBO_MAC at the top of controle_cripto.py "
                     "(use ferramentas/mostra_mac.py on the robot to find it).")
if len(CHAVE) != 16:
    raise SystemExit("CHAVE must be exactly 16 bytes.")

# ---------- Cifra ----------
def cifrar(cmd):
    # 16 bytes: comando no byte 0, resto aleatorio (esconde e evita cifras iguais).
    bloco = bytes([ord(cmd[0])]) + os.urandom(15)
    return cryptolib.aes(CHAVE, MODO_ECB).encrypt(bloco)

# ---------- Radio ESP-NOW ----------
def mac_str(b):
    return ':'.join('%02x' % x for x in b)

sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.disconnect()
sta.config(channel=CANAL)
sta.config(pm=sta.PM_NONE)

e = espnow.ESPNow()
e.config(rxbuf=2048)
e.active(True)
e.add_peer(ROBO_MAC)          # unicast: precisa registrar o destino para enviar

print("=" * 40)
print("Role  : ENCRYPTED UNICAST controller (buttons)")
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

CORES = {"F": (0, 40, 0), "T": (40, 0, 0), "P": (0, 0, 8)}

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
        e.send(ROBO_MAC, cifrar(cmd))         # <-- manda a CIFRA, so para o robo
    except OSError as erro:
        print("send failed", cmd, erro)
        return
    seq += 1
    print("[%d] sent (encrypted, unicast): %s" % (seq, cmd))
    led(cmd)

def comando_atual():
    f, t = apertado(btn_frente), apertado(btn_tras)
    if f and not t:
        return "F"
    if t and not f:
        return "T"
    return "P"

# ---------- Laco principal (igual ao controle.py: so envia na mudanca) ----------
ultimo = "P"
led(ultimo)
while True:
    cmd = comando_atual()
    if cmd != ultimo:
        time.sleep_ms(20)
        if comando_atual() == cmd:
            enviar(cmd)
            ultimo = cmd
    time.sleep_ms(10)
