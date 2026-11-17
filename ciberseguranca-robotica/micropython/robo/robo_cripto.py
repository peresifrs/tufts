# robo_cripto.py - ROBO que DECIFRA o comando antes de mover (ESP-NOW + BLE, sem PC).
#
# Igual ao robo.py, mas espera blocos de 16 bytes cifrados em AES (controle_cripto.py).
# A CHAVE e a mesma do controle. Decifra, le o byte 0 (o comando) e move o motor.
#
# A LICAO: a cifra garante confidencialidade (o espiao nao le o comando), mas NAO
# garante autenticidade. O robo aceita QUALQUER bloco que decifre bem - inclusive
# um bloco capturado e reenviado pelo espiao (replay). Sem numero de sequencia/nonce
# nao ha como saber que aquele bloco ja foi usado.
#
# Placa testada: M5Stack Capsule (UiFlow2, /flash). Mesmo preparo do robo.py:
#   mpremote connect <porta-robo> mip install --target=/flash/libs aioble   # uma vez
#   mpremote connect <porta-robo> fs cp micropython/robo/lego_motor.py :/flash/lego_motor.py
#   mpremote connect <porta-robo> fs cp micropython/robo/robo_cripto.py :/flash/main.py

import network
import espnow
import uasyncio as asyncio

try:
    import cryptolib
except ImportError:
    import ucryptolib as cryptolib

from lego_motor import LEGOEducationMotor


CANAL = 1
CARD_SERIAL = "7551"
VEL = 20
INVERTER_ESQUERDO = True          # mesmo ajuste do robo.py (motor esquerdo invertido)
INVERTER_DIREITO = False

# CHAVE AES de 16 bytes. DEVE ser IDENTICA ao controle_cripto.py.
CHAVE = b"ciberseg-aes-key"
MODO_ECB = 1

CMDS = {
    "F": (VEL, VEL),
    "T": (-VEL, -VEL),
    "E": (-VEL, VEL),
    "D": (VEL, -VEL),
}

def decifrar(bloco):
    # Decifra os 16 bytes e devolve o comando (byte 0). None se vier tamanho errado.
    if bloco is None or len(bloco) != 16:
        return None
    claro = cryptolib.aes(CHAVE, MODO_ECB).decrypt(bloco)
    try:
        return chr(claro[0]).upper()
    except Exception:
        return None

sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.disconnect()
sta.config(channel=CANAL)
sta.config(pm=sta.PM_NONE)

e = espnow.ESPNow()
e.config(rxbuf=2048)
e.active(True)


async def executar_comando(motor, comando):
    if comando == "P":
        await motor.stop(motor=0)
        await motor.stop(motor=1)
        print("CMD:P")
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
    print("CMD:{} ({}, {})".format(comando, esquerda, direita))


async def main():
    motor = LEGOEducationMotor(card_serial=CARD_SERIAL)
    try:
        print("Connecting to LEGO BLE motor, card", CARD_SERIAL)
        await motor.connect()
        print(
            "ENCRYPTED ROBOT ready, channel {}, motor {}".format(
                sta.config("channel"), motor.device_serial
            )
        )

        while True:
            host, msg = e.recv(0)
            if msg is not None:
                comando = decifrar(msg)
                if comando is None:
                    print("Invalid block from", host)
                else:
                    await executar_comando(motor, comando)

            await asyncio.sleep_ms(5)
    finally:
        await motor.disconnect()


asyncio.run(main())
