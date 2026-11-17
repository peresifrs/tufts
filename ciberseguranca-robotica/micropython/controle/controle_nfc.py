# controle_nfc.py - CONTROLE por gesto na varinha (XIAO ESP32-C6) com MODO trocado por CARTAO NFC.
#
# Mesmo gesto do controle_varinha.py (segure o BOTAO e incline: F/T/E/D; soltou = P).
# Com o botao SOLTO, encoste um cartao no leitor NFC da varinha para trocar o modo:
#
#   versao 1  broadcast  texto claro, para todos   -> espiao.py le e repete
#   versao 2  unicast    texto claro, so p/ ROBO_MAC -> espiao comum fica cego; o de
#                                                      modo monitor (arduino/) le e repete
#   versao 3  cripto     AES-128 + unicast          -> monitor nao le, mas repete e o robo obedece
#
# O robo correspondente e robo/robo_modos.py: encoste o MESMO cartao nele tambem.
# No modo cripto o robo recusa texto claro. CARTOES deve ser identico nos dois.
# A CHAVE ainda e fixa no codigo (igual ao robo); depois ela vai para o cartao.
#
# Ao ler um cartao, a matriz mostra o numero da versao (1/2/3) e o ponto de
# "parado" fica na cor do modo: branco = broadcast, amarelo = unicast, roxo = cripto.
#
# CARTOES: qualquer cartao serve, sem regravar. Encoste um cartao desconhecido e o
# UID aparece no terminal; copie para o dicionario CARTOES abaixo. Cartoes com
# texto NDEF "broadcast", "unicast" ou "cripto" (ou "modo:<nome>") funcionam sem cadastro.
#
# Preparo (uma vez): o driver do leitor vem do firmware original da varinha.
#   mpremote connect <porta> fs cp legado/varinha_original/lib/pn532.py :/lib/pn532.py
#   mpremote connect <porta> fs cp legado/varinha_original/lib/nfc_reader.py :/lib/nfc_reader.py
#   mpremote connect <porta> fs cp micropython/controle/controle_nfc.py :/main.py
#
# Hardware: botao GPIO0 | I2C SDA 22, SCL 23 com LIS2DW12 (0x19) e PN532 (0x24)
#           matriz 5x5 WS2812 no GPIO20 | vibracall GPIO21 | LED de energia GPIO2

import network
import espnow
import time
import struct
import os
from machine import Pin, SoftI2C

try:
    import cryptolib
except ImportError:
    import ucryptolib as cryptolib

# ====================== CONFIGURACAO ======================
CANAL = 1
BROADCAST = b'\xff' * 6
ROBO_MAC = b'\xa0\xf2\x62\x87\xaf\x74'   # varinha do robo

# CHAVE AES de 16 bytes. DEVE ser IDENTICA no robo_modos.py.
CHAVE = b"ciberseg-aes-key"
MODO_ECB = 1

# UID do cartao (como aparece no terminal) -> modo.
CARTOES = {
    # "04:A1:B2:C3:D4:E5:80": "broadcast",
    "04:60:1E:82:87:1F:94": "unicast",
    "04:4E:36:8A:D4:14:91": "crypto",
}
MODO_INICIAL = "broadcast"

PINO_BOTAO = 0
PINO_SDA, PINO_SCL = 22, 23
PINO_MATRIZ = 20          # None desliga a matriz de LEDs
PINO_VIBRA = 21           # vibracall: deixado desligado
PINO_LED_ENERGIA = 2
NFC_ADDR = 0x24
NFC_INTERVALO_MS = 300    # de quanto em quanto tempo procura cartao (botao solto)

# Eixos calibrados (2026-11-16), varinha em pe como joystick: frente = -Z, direita = +Y.
EIXO_FRENTE = ('z', -1)
EIXO_LADO = ('y', +1)

LIMIAR = 0.35
HISTERESE = 0.10
ESTAVEL_MS = 60
DEBUG = False             # True imprime as inclinacoes enquanto o botao esta apertado
# ==========================================================

# ---------- Configuracao da EQUIPE (corrida com varios conjuntos) ----------
# Se existir /lib/equipe.py na placa, ele substitui CANAL, ROBO_MAC, CHAVE,
# CARD_SERIAL, CARTOES... Assim o main.py e IGUAL em todas as equipes.
# Sem equipe.py valem os valores acima (equipe 1).
EQUIPE = 1
COR_EQUIPE = None         # (r, g, b): pisca a matriz inteira nessa cor ao ligar
try:
    from equipe import *
except ImportError:
    pass

MODOS = {
    #  nome         versao  cor do modo
    "broadcast": ("1", (12, 12, 12)),
    "unicast":   ("2", (25, 20, 0)),
    "crypto":    ("3", (20, 0, 25)),
}

if len(CHAVE) != 16:
    raise SystemExit("CHAVE must be exactly 16 bytes.")

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
e.add_peer(ROBO_MAC)

# ---------- Saidas fixas da placa ----------
try:
    Pin(PINO_VIBRA, Pin.OUT, value=0)
    Pin(PINO_LED_ENERGIA, Pin.OUT, value=1)
except Exception:
    pass

# ---------- Acelerometro LIS2DW12 ----------
ACC_ADDR = 0x19
ESCALA = 0.000122
_IDX = {'x': 0, 'y': 1, 'z': 2}

i2c = SoftI2C(sda=Pin(PINO_SDA), scl=Pin(PINO_SCL), freq=100000)
if i2c.readfrom_mem(ACC_ADDR, 0x0F, 1)[0] != 0x44:
    raise SystemExit("LIS2DW12 accelerometer not found at 0x19")
i2c.writeto_mem(ACC_ADDR, 0x21, b'\x40')
time.sleep_ms(10)
i2c.writeto_mem(ACC_ADDR, 0x20, b'\x54')
i2c.writeto_mem(ACC_ADDR, 0x25, b'\x14')
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

# ---------- Leitor NFC PN532 (opcional: sem ele, fica no MODO_INICIAL) ----------
nfc = None
read_ndef_text = None
try:
    from pn532 import PN532
    nfc = PN532(i2c, NFC_ADDR)
    nfc.begin()
    # RFConfiguration (0x32), item 5: tentar UMA vez e responder "nenhum cartao"
    # na hora, em vez de ficar procurando (senao cada consulta trava o laco).
    nfc._send_command(0x32, b'\x05\xff\x01\x01')
    try:
        from nfc_reader import read_ndef_text
    except ImportError:
        read_ndef_text = None      # sem nfc_reader: so reconhece cartoes por UID
except Exception as erro:
    print("NFC unavailable (%s): fixed mode %s" % (erro, MODO_INICIAL))
    nfc = None

def ler_cartao():
    """Devolve (uid_hex, texto) se ha cartao no leitor, senao (None, None)."""
    try:
        tag = nfc.read_passive_target(timeout=100)
    except Exception:
        return None, None
    if tag is None:
        return None, None
    uid = tag['uid_hex']
    texto = None
    if uid not in CARTOES and read_ndef_text is not None:
        try:
            texto, _ = read_ndef_text(nfc, timeout=100)
        except Exception:
            texto = None
    return uid, texto

def modo_do_cartao(uid, texto):
    if uid in CARTOES:
        return CARTOES[uid]
    if texto:
        t = texto.strip().lower()
        if t.startswith("modo:"):
            t = t[5:]
        if t == "cripto":
            t = "crypto"          # aceita o nome em portugues no cartao
        if t in MODOS:
            return t
    return None

# ---------- Matriz de LEDs 5x5 (opcional) ----------
_np = None
if PINO_MATRIZ is not None:
    try:
        import neopixel
        _np = neopixel.NeoPixel(Pin(PINO_MATRIZ, Pin.OUT), 25)
    except Exception:
        _np = None

# indice = linha*5 + coluna
FORMAS = {
    "F": ((2, 6, 7, 8, 10, 12, 14, 17, 22), (0, 30, 0)),
    "T": ((22, 16, 17, 18, 10, 12, 14, 7, 2), (30, 0, 0)),
    "E": ((10, 6, 11, 16, 2, 12, 22, 13, 14), (25, 20, 0)),
    "D": ((14, 8, 13, 18, 2, 12, 22, 11, 10), (0, 15, 30)),
    "?": ((6, 8, 12, 16, 18), (15, 15, 15)),
    "!": ((0, 4, 6, 8, 12, 16, 18, 20, 24), (30, 0, 0)),   # X vermelho: cartao desconhecido
}
DIGITOS = {
    "1": (2, 6, 7, 12, 17, 21, 22, 23),
    "2": (1, 2, 3, 8, 11, 12, 13, 16, 21, 22, 23),
    "3": (1, 2, 3, 8, 11, 12, 13, 18, 21, 22, 23),
}

modo = MODO_INICIAL

def _pintar(idx, cor):
    if _np is None:
        return
    try:
        for i in range(25):
            _np[i] = (0, 0, 0)
        for i in idx:
            _np[i] = cor
        _np.write()
    except Exception:
        pass

def mostrar(chave):
    if chave == "P":                       # parado: ponto central na cor do modo
        _pintar((12,), MODOS[modo][1])
    else:
        _pintar(*FORMAS.get(chave, ((), (0, 0, 0))))

def mostrar_modo():
    versao, cor = MODOS[modo]
    _pintar(DIGITOS[versao], cor)

# ---------- Envio (depende do modo) ----------
def cifrar(cmd):
    # 16 bytes: comando no byte 0, resto aleatorio (o mesmo comando vira cifras diferentes).
    bloco = bytes([ord(cmd[0])]) + os.urandom(15)
    return cryptolib.aes(CHAVE, MODO_ECB).encrypt(bloco)

seq = 0

def enviar(cmd):
    global seq
    try:
        if modo == "broadcast":
            e.send(BROADCAST, cmd.encode())
        elif modo == "unicast":
            e.send(ROBO_MAC, cmd.encode())
        else:
            e.send(ROBO_MAC, cifrar(cmd))
    except OSError as erro:
        print("send failed", cmd, erro)
        return False
    seq += 1
    print("[%d] sent (%s): %s" % (seq, modo, cmd))
    mostrar(cmd)
    return True

def trocar_modo(novo):
    global modo
    if novo == modo:
        return
    modo = novo
    print(">>> MODE: %s (version %s)" % (modo, MODOS[modo][0]))
    mostrar_modo()
    time.sleep_ms(800)
    mostrar("P")

# ---------- Gesto -> comando ----------
def direcao(frente, lado, atual):
    limiar_sai = LIMIAR - HISTERESE
    if atual == "F" and frente > limiar_sai and frente >= abs(lado):
        return "F"
    if atual == "T" and -frente > limiar_sai and -frente >= abs(lado):
        return "T"
    if atual == "D" and lado > limiar_sai and lado >= abs(frente):
        return "D"
    if atual == "E" and -lado > limiar_sai and -lado >= abs(frente):
        return "E"
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
    return None

# ---------- Laco principal ----------
botao = Pin(PINO_BOTAO, Pin.IN, Pin.PULL_UP)

print("=" * 40)
print("Role  : controller (wand: gesture + NFC card mode), team %d" % EQUIPE)
print("MAC   :", mac_str(sta.config('mac')))
print("Robot :", mac_str(ROBO_MAC))
print("Chan  :", sta.config('channel'), "(expected %d)" % CANAL)
print("NFC   :", "ok" if nfc else "missing")
print("Mode  : %s (version %s)" % (modo, MODOS[modo][0]))
print("=" * 40)

enviado = "P"
if COR_EQUIPE:
    _pintar(range(25), COR_EQUIPE)
    time.sleep_ms(1000)
mostrar_modo()
time.sleep_ms(800)
mostrar("P")
apertado_antes = False
ref = None
candidato, desde = None, 0
t_debug = 0
t_nfc = 0
uid_anterior = None       # evita repetir a mensagem enquanto o cartao fica encostado

while True:
    apertado = botao.value() == 0

    if apertado and not apertado_antes:
        time.sleep_ms(20)
        if botao.value() == 0:
            ref = media_acc()
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

    agora = time.ticks_ms()

    if apertado:
        a = ler_acc()
        d = (a[0] - ref[0], a[1] - ref[1], a[2] - ref[2])
        frente, lado = componente(d, EIXO_FRENTE), componente(d, EIXO_LADO)
        cmd = direcao(frente, lado, enviado)

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

    elif nfc is not None and time.ticks_diff(agora, t_nfc) >= NFC_INTERVALO_MS:
        # Botao solto: procura cartao (so aqui, para nao atrasar o gesto).
        t_nfc = agora
        uid, texto = ler_cartao()
        if uid is not None and uid != uid_anterior:
            novo = modo_do_cartao(uid, texto)
            if novo is None:
                print("unknown card: UID=%s text=%r" % (uid, texto))
                print('  add to CARTOES: "%s": "broadcast"|"unicast"|"crypto",' % uid)
                _pintar(*FORMAS["!"])
                time.sleep_ms(600)
                mostrar("P")
            else:
                trocar_modo(novo)
        uid_anterior = uid

    time.sleep_ms(10)
