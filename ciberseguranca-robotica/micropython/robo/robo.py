# robo.py - ROBO: recebe comandos por ESP-NOW e move o motor LEGO por BLE, sem PC.
#
# Obedece a QUALQUER comando que chegar no canal (F/T/E/D/P), venha do controle
# ou do espiao (replay) - nao ha como saber quem mandou. Essa e a licao.
#
# Placa testada: M5Stack Capsule (firmware UiFlow2, filesystem em /flash).
#   mpremote connect <porta-robo> mip install --target=/flash/libs aioble   # uma vez
#   mpremote connect <porta-robo> fs cp micropython/robo/lego_motor.py :/flash/lego_motor.py
#   mpremote connect <porta-robo> fs cp micropython/robo/robo.py :/flash/main.py
#
# CARD_SERIAL = numero do Connection Card do motor LEGO.

import network
import espnow
import uasyncio as asyncio

from lego_motor import LEGOEducationMotor


CANAL = 1
CARD_SERIAL = "7551"
VEL = 20
INVERTER_ESQUERDO = True
INVERTER_DIREITO = False

CMDS = {
    "F": (VEL, VEL),
    "T": (-VEL, -VEL),
    "E": (-VEL, VEL),
    "D": (VEL, -VEL),
}

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
        print("Comando desconhecido:", comando)
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
        print("Conectando ao motor LEGO BLE, cartao", CARD_SERIAL)
        await motor.connect()
        print(
            "ROBO BLE pronto, canal {}, motor {}".format(
                sta.config("channel"), motor.device_serial
            )
        )

        while True:
            host, msg = e.recv(0)
            if msg is not None:
                try:
                    texto = msg.decode().strip().upper()
                except UnicodeError:
                    print("Mensagem ESP-NOW invalida de", host)
                else:
                    if texto:
                        await executar_comando(motor, texto[:1])

            await asyncio.sleep_ms(5)
    finally:
        await motor.disconnect()


asyncio.run(main())
