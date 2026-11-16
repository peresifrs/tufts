import uasyncio as asyncio

from lego_motor import LEGOEducationMotor


CARD_SERIAL = "7551"


async def main():
    motor = LEGOEducationMotor(card_serial=CARD_SERIAL)
    try:
        print("Procurando motor LEGO, Connection Card", CARD_SERIAL)
        await motor.connect()
        print("Motor conectado. Teste em velocidade baixa.")
        await motor.run(speed=20, motor=0)
        await asyncio.sleep_ms(1000)
    finally:
        await motor.disconnect()
        print("Teste encerrado.")


asyncio.run(main())
