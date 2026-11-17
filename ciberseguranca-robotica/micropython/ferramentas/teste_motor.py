import uasyncio as asyncio

from lego_motor import LEGOEducationMotor


CARD_SERIAL = "7551"


async def main():
    motor = LEGOEducationMotor(card_serial=CARD_SERIAL)
    try:
        print("Searching for LEGO motor, Connection Card", CARD_SERIAL)
        await motor.connect()
        print("Motor connected. Low-speed test.")
        await motor.run(speed=20, motor=0)
        await asyncio.sleep_ms(1000)
    finally:
        await motor.disconnect()
        print("Test finished.")


asyncio.run(main())
