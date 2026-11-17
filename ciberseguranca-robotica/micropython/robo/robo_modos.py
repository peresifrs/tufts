# robo_modos.py - ROBO dos 3 modos do controle_nfc.py, com MODO trocado por CARTAO NFC.
#
# Encoste o MESMO cartao no controle e no robo. O robo so aceita o formato do modo:
#   broadcast / unicast (versoes 1 e 2): so pacotes de 1 byte (texto claro)
#   cripto (versao 3)                  : so blocos AES de 16 bytes; texto claro e RECUSADO
#
# (Para o robo, broadcast e unicast sao iguais: o ESP-NOW nao diz se o pacote veio
#  enderecado a ele ou a todos. Quem muda e o controle.)
#
# A LICAO continua: no modo cripto o espiao nao le o comando e nao consegue injetar
# texto claro, mas pode REPETIR um bloco cifrado capturado - e o robo obedece.
# A CHAVE ainda e fixa no codigo (igual ao controle); depois ela vai para o cartao.
#
# Varinha XIAO ESP32-C6 (MicroPython 1.28, sem /flash). Preparo:
#   lego_motor.py e aioble em /lib (como no robo.py)
#   mpremote connect <porta> fs cp legado/varinha_original/lib/pn532.py :/lib/pn532.py
#   mpremote connect <porta> fs cp legado/varinha_original/lib/nfc_reader.py :/lib/nfc_reader.py
#   mpremote connect <porta> fs cp micropython/robo/robo_modos.py :/main.py

import network
import espnow
import time
import uasyncio as asyncio
from machine import Pin, SoftI2C

try:
    import cryptolib
except ImportError:
    import ucryptolib as cryptolib

from lego_motor import LEGOEducationMotor


CANAL = 1
CARD_SERIAL = "7551"
VEL = 20
INVERTER_ESQUERDO = True
INVERTER_DIREITO = False

# CHAVE AES de 16 bytes. DEVE ser IDENTICA ao controle_nfc.py.
CHAVE = b"ciberseg-aes-key"
MODO_ECB = 1

# UID do cartao -> modo. DEVE ser IDENTICO ao CARTOES do controle_nfc.py.
CARTOES = {
    # "04:A1:B2:C3:D4:E5:80": "broadcast",
    "04:60:1E:82:87:1F:94": "unicast",
    "04:4E:36:8A:D4:14:91": "crypto",
}
MODO_INICIAL = "broadcast"

PINO_SDA, PINO_SCL = 22, 23
PINO_MATRIZ = 20          # None desliga a matriz de LEDs
NFC_ADDR = 0x24
NFC_INTERVALO_MS = 300

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

CMDS = {
    "F": (VEL, VEL),
    "T": (-VEL, -VEL),
    "E": (-VEL, VEL),
    "D": (VEL, -VEL),
}

MODOS = {
    #  nome         versao  cor     tamanho aceito
    "broadcast": ("1", (12, 12, 12), 1),
    "unicast":   ("2", (25, 20, 0), 1),
    "crypto":    ("3", (20, 0, 25), 16),
}

modo = MODO_INICIAL

# ---------- Radio ESP-NOW ----------
sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.disconnect()
sta.config(channel=CANAL)
sta.config(pm=sta.PM_NONE)

e = espnow.ESPNow()
e.config(rxbuf=2048)
e.active(True)

# ---------- Leitor NFC PN532 (opcional: sem ele, fica no MODO_INICIAL) ----------
nfc = None
read_ndef_text = None
try:
    from pn532 import PN532
    i2c = SoftI2C(sda=Pin(PINO_SDA), scl=Pin(PINO_SCL), freq=100000)
    nfc = PN532(i2c, NFC_ADDR)
    nfc.begin()
    # RFConfiguration (0x32), item 5: tentar uma vez e responder "nenhum cartao"
    # na hora, para a leitura nao travar o BLE do motor.
    nfc._send_command(0x32, b'\x05\xff\x01\x01')
    try:
        from nfc_reader import read_ndef_text
    except ImportError:
        read_ndef_text = None
except Exception as erro:
    print("NFC unavailable (%s): fixed mode %s" % (erro, MODO_INICIAL))
    nfc = None

def ler_cartao():
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

DIGITOS = {
    "1": (2, 6, 7, 12, 17, 21, 22, 23),
    "2": (1, 2, 3, 8, 11, 12, 13, 16, 21, 22, 23),
    "3": (1, 2, 3, 8, 11, 12, 13, 18, 21, 22, 23),
}
X_VERMELHO = ((0, 4, 6, 8, 12, 16, 18, 20, 24), (30, 0, 0))

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

def mostrar_modo():
    versao, cor, _ = MODOS[modo]
    _pintar(DIGITOS[versao], cor)

# ---------- Pacote -> comando (so no formato do modo atual) ----------
def interpretar(msg):
    """Devolve (comando, None) ou (None, motivo da recusa)."""
    tamanho = MODOS[modo][2]
    if len(msg) != tamanho:
        return None, "%dB, mode %s expects %dB" % (len(msg), modo, tamanho)
    if tamanho == 1:
        return chr(msg[0]).upper(), None
    claro = cryptolib.aes(CHAVE, MODO_ECB).decrypt(msg)
    return chr(claro[0]).upper(), None


async def parar(motor):
    await motor.stop(motor=0)
    await motor.stop(motor=1)


async def executar_comando(motor, comando):
    if comando == "P":
        await parar(motor)
        print("CMD:P (%s)" % modo)
        return

    velocidades = CMDS.get(comando)
    if velocidades is None:
        print("Unknown command:", comando)
        return

    esquerda, direita = velocidades
    if INVERTER_ESQUERDO:
        esquerda = -esquerda
    if INVERTER_DIREITO:
        direita = -direita

    await motor.run_tank(esquerda, direita)
    print("CMD:{} ({}, {}) ({})".format(comando, esquerda, direita, modo))


async def verificar_cartao(motor, uid_anterior):
    """Le o NFC; troca o modo se for um cartao conhecido. Devolve o UID visto."""
    global modo
    uid, texto = ler_cartao()
    if uid is None or uid == uid_anterior:
        return uid
    novo = modo_do_cartao(uid, texto)
    if novo is None:
        print("unknown card: UID=%s text=%r" % (uid, texto))
        print('  add to CARTOES: "%s": "broadcast"|"unicast"|"crypto",' % uid)
        _pintar(*X_VERMELHO)
        await asyncio.sleep_ms(600)
        mostrar_modo()
    elif novo != modo:
        modo = novo
        await parar(motor)                # trocar de modo sempre para o robo
        print(">>> MODE: %s (version %s)" % (modo, MODOS[modo][0]))
        mostrar_modo()
    return uid


async def main():
    motor = LEGOEducationMotor(card_serial=CARD_SERIAL)
    try:
        print("Connecting to LEGO BLE motor, card", CARD_SERIAL)
        await motor.connect()
        print("ROBOT team {} ready, channel {}, motor {}, NFC {}, mode {}".format(EQUIPE,
            sta.config("channel"), motor.device_serial,
            "ok" if nfc else "missing", modo))
        if COR_EQUIPE:
            _pintar(range(25), COR_EQUIPE)
            await asyncio.sleep_ms(1000)
        mostrar_modo()

        t_nfc = time.ticks_ms()
        uid_anterior = None
        while True:
            host, msg = e.recv(0)
            if msg is not None:
                comando, recusa = interpretar(msg)
                if comando is not None:
                    await executar_comando(motor, comando)
                elif len(msg) in (1, 16):
                    # 1 ou 16 B no formato errado: tentativa no modo errado (ex.: texto
                    # claro no modo cripto). JSON das outras varinhas e ignorado calado.
                    print("REJECTED from", ':'.join('%02x' % b for b in host), "-", recusa)

            if nfc is not None and time.ticks_diff(time.ticks_ms(), t_nfc) >= NFC_INTERVALO_MS:
                t_nfc = time.ticks_ms()
                uid_anterior = await verificar_cartao(motor, uid_anterior)

            await asyncio.sleep_ms(5)
    finally:
        await motor.disconnect()


asyncio.run(main())
