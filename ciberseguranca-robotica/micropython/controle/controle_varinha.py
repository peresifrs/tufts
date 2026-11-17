# controle_varinha.py - CONTROLE por gesto na varinha (Seeed XIAO ESP32-C6), sem PC.
#
# Segure o BOTAO e incline a varinha:
#   para frente  -> "F"      para tras   -> "T"
#   para esquerda-> "E"      para direita-> "D"
#   soltou o botao -> "P" (parar)
#
# A direcao e medida RELATIVA a posicao em que a varinha estava no instante em
# que o botao foi apertado: nao importa como a pessoa segura, o "zero" e ali.
# Voltar ao centro com o botao apertado NAO para o robo; so soltar o botao para.
#
# Versao 1 (broadcast, texto claro): o robo obedece e o ESPIAO ouve e repete.
#
# Grave na placa como main.py:
#   mpremote connect <porta-varinha> fs cp micropython/controle/controle_varinha.py :/main.py
#
# Hardware da varinha (de lib/hubtype.py do firmware original, backup em legado/):
#   botao GPIO0 (pull-up, apertado = 0) | LIS2DW12 I2C 0x19, SDA 22, SCL 23
#   matriz 5x5 WS2812 no GPIO20 | vibracall GPIO21 | LED de energia GPIO2

import network
import espnow
import time
import struct
from machine import Pin, SoftI2C

# ====================== CONFIGURACAO ======================
CANAL = 1
BROADCAST = b'\xff' * 6

PINO_BOTAO = 0
PINO_SDA, PINO_SCL = 22, 23
PINO_MATRIZ = 20          # None desliga a matriz de LEDs
PINO_VIBRA = 21           # vibracall: deixado desligado
PINO_LED_ENERGIA = 2

# Quais eixos do acelerometro sao "frente" e "lado", e o sinal de cada um.
# Calibrado (2026-11-16) com a varinha segura em pe, como joystick:
#   ponta = -X (nao use: muda com QUALQUER inclinacao), frente = -Z, direita = +Y.
# Para recalibrar: DEBUG = True, incline e veja qual numero muda.
EIXO_FRENTE = ('z', -1)   # ('x'|'y'|'z', +1|-1)
EIXO_LADO = ('y', +1)     # positivo = direita

LIMIAR = 0.35             # inclinacao (em g) para valer como direcao (~20 graus)
HISTERESE = 0.10          # precisa cair abaixo de LIMIAR-HISTERESE para sair
ESTAVEL_MS = 60           # direcao precisa se manter esse tempo antes de enviar
DEBUG = True              # imprime as inclinacoes enquanto o botao esta apertado
# ==========================================================

def mac_str(b):
    return ':'.join('%02x' % x for x in b)

# ---------- Radio ESP-NOW ----------
sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.disconnect()
sta.config(channel=CANAL)
sta.config(pm=sta.PM_NONE)

e = espnow.ESPNow()
e.config(rxbuf=2048)
e.active(True)
e.add_peer(BROADCAST)

# ---------- Saidas fixas da placa ----------
try:
    Pin(PINO_VIBRA, Pin.OUT, value=0)
    Pin(PINO_LED_ENERGIA, Pin.OUT, value=1)
except Exception:
    pass

# ---------- Acelerometro LIS2DW12 (so registradores, sem biblioteca) ----------
ACC_ADDR = 0x19
ESCALA = 0.000122         # g por LSB em +-4 g
_IDX = {'x': 0, 'y': 1, 'z': 2}

i2c = SoftI2C(sda=Pin(PINO_SDA), scl=Pin(PINO_SCL), freq=100000)
if i2c.readfrom_mem(ACC_ADDR, 0x0F, 1)[0] != 0x44:
    raise SystemExit("LIS2DW12 accelerometer not found at 0x19")
i2c.writeto_mem(ACC_ADDR, 0x21, b'\x40')   # CTRL2: soft reset
time.sleep_ms(10)
i2c.writeto_mem(ACC_ADDR, 0x20, b'\x54')   # CTRL1: 100 Hz, alto desempenho
i2c.writeto_mem(ACC_ADDR, 0x25, b'\x14')   # CTRL6: +-4 g, baixo ruido
time.sleep_ms(20)

def ler_acc():
    d = i2c.readfrom_mem(ACC_ADDR, 0x28, 6)
    x, y, z = struct.unpack('<hhh', d)
    return (x * ESCALA, y * ESCALA, z * ESCALA)

def media_acc(n=8):
    s = [0.0, 0.0, 0.0]
    for _ in range(n):
        a = ler_acc()
        for k in range(3):
            s[k] += a[k]
        time.sleep_ms(10)
    return [v / n for v in s]

def componente(a, eixo):
    nome, sinal = eixo
    return a[_IDX[nome]] * sinal

# ---------- Matriz de LEDs 5x5 (opcional: nunca derruba o programa) ----------
_np = None
if PINO_MATRIZ is not None:
    try:
        import neopixel
        _np = neopixel.NeoPixel(Pin(PINO_MATRIZ, Pin.OUT), 25)
    except Exception:
        _np = None

# indice = linha*5 + coluna
FORMAS = {
    "F": ((2, 6, 7, 8, 10, 12, 14, 17, 22), (0, 30, 0)),    # seta p/ cima, verde
    "T": ((22, 16, 17, 18, 10, 12, 14, 7, 2), (30, 0, 0)),  # seta p/ baixo, vermelho
    "E": ((10, 6, 11, 16, 2, 12, 22, 13, 14), (25, 20, 0)), # seta p/ esquerda, amarelo
    "D": ((14, 8, 13, 18, 2, 12, 22, 11, 10), (0, 15, 30)), # seta p/ direita, azul
    "P": ((12,), (0, 0, 10)),                               # ponto azul fraco
    "?": ((6, 8, 12, 16, 18), (15, 15, 15)),                # botao apertado, sem direcao
}

def mostrar(chave):
    if _np is None:
        return
    try:
        idx, cor = FORMAS.get(chave, ((), (0, 0, 0)))
        for i in range(25):
            _np[i] = (0, 0, 0)
        for i in idx:
            _np[i] = cor
        _np.write()
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
        return False
    seq += 1
    print("[%d] sent: %s" % (seq, cmd))
    mostrar(cmd)
    return True

# ---------- Gesto -> comando ----------
def direcao(frente, lado, atual):
    """Comando para a inclinacao (frente, lado), com histerese sobre o atual."""
    limiar_sai = LIMIAR - HISTERESE
    # se ja esta numa direcao e ela ainda vale (acima do limiar de saida), mantem
    if atual == "F" and frente > limiar_sai and frente >= abs(lado):
        return "F"
    if atual == "T" and -frente > limiar_sai and -frente >= abs(lado):
        return "T"
    if atual == "D" and lado > limiar_sai and lado >= abs(frente):
        return "D"
    if atual == "E" and -lado > limiar_sai and -lado >= abs(frente):
        return "E"
    # senao, escolhe o eixo dominante se passar do limiar
    if abs(frente) >= abs(lado):
        if frente > LIMIAR:
            return "F"
        if frente < -LIMIAR:
            return "T"
    else:
        if lado > LIMIAR:
            return "D"
        if lado < -LIMIAR:
            return "E"
    return None           # centro: nao muda nada

# ---------- Laco principal ----------
botao = Pin(PINO_BOTAO, Pin.IN, Pin.PULL_UP)

print("=" * 40)
print("Role  : controller (wand: button + accelerometer)")
print("MAC   :", mac_str(sta.config('mac')))
print("Chan  :", sta.config('channel'), "(expected %d)" % CANAL)
print("Axes  : fwd=%s%s  side=%s%s" % (EIXO_FRENTE[0], '+' if EIXO_FRENTE[1] > 0 else '-',
                                          EIXO_LADO[0], '+' if EIXO_LADO[1] > 0 else '-'))
print("=" * 40)

enviado = "P"             # ultimo comando enviado
mostrar("P")
apertado_antes = False
ref = None
candidato, desde = None, 0
t_debug = 0

while True:
    apertado = botao.value() == 0

    if apertado and not apertado_antes:
        time.sleep_ms(20)                          # debounce
        if botao.value() == 0:
            ref = media_acc()                      # o "zero" e onde a varinha esta agora
            candidato = None
            apertado_antes = True
            mostrar("?")
            if DEBUG:
                print("button: ref = %.2f %.2f %.2f" % tuple(ref))
        continue

    if not apertado and apertado_antes:
        time.sleep_ms(20)
        if botao.value() == 1:
            apertado_antes = False
            if enviado != "P":
                if enviar("P"):
                    enviado = "P"
            else:
                mostrar("P")
        continue

    if apertado:
        a = ler_acc()
        d = (a[0] - ref[0], a[1] - ref[1], a[2] - ref[2])
        frente, lado = componente(d, EIXO_FRENTE), componente(d, EIXO_LADO)
        cmd = direcao(frente, lado, enviado)

        agora = time.ticks_ms()
        if DEBUG and time.ticks_diff(agora, t_debug) > 250:
            t_debug = agora
            print("dx=%+.2f dy=%+.2f dz=%+.2f  fwd=%+.2f side=%+.2f  -> %s"
                  % (d[0], d[1], d[2], frente, lado, cmd))

        if cmd is not None and cmd != enviado:
            if cmd != candidato:
                candidato, desde = cmd, agora
            elif time.ticks_diff(agora, desde) >= ESTAVEL_MS:
                if enviar(cmd):
                    enviado = cmd
                candidato = None
        else:
            candidato = None

    time.sleep_ms(10)
