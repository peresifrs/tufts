"""Controle básico BLE/RPC de motores LEGO Education no MicroPython.

Implementação independente e reduzida para dispositivos Single Motor e
Double Motor; não é um porte integral da biblioteca legoeducation.
"""

import struct

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

import aioble
import bluetooth


SERVICE_UUID = bluetooth.UUID("0000FD02-0000-1000-8000-00805F9B34FB")
ADVERTISEMENT_SERVICE_UUID = bluetooth.UUID(0xFD02)
WRITE_UUID = bluetooth.UUID("0000FD02-0001-1000-8000-00805F9B34FB")
NOTIFY_UUID = bluetooth.UUID("0000FD02-0002-1000-8000-00805F9B34FB")

LEGO_COMPANY_ID = 0x0397
PRODUCT_SINGLE_MOTOR = 512
PRODUCT_DOUBLE_MOTOR = 513

INFO_REQUEST = 0
INFO_RESPONSE = 1
MOTOR_RUN = 122
MOTOR_RUN_RESULT = 123
MOTOR_RUN_FOR_TIME = 126
MOTOR_RUN_FOR_TIME_RESULT = 127
MOTOR_STOP = 138
MOTOR_STOP_RESULT = 139
MOTOR_SET_SPEED = 140
MOTOR_SET_SPEED_RESULT = 141
ERROR_REPORT_RESPONSE = 3

CARD_SERIAL = "7551"
SCAN_DURATION_MS = 12000
RESPONSE_TIMEOUT_MS = 5000


def _validate_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("{} deve ser um inteiro".format(name))


def _validate_speed(speed):
    _validate_int(speed, "speed")
    if speed < -100 or speed > 100:
        raise ValueError("speed deve estar entre -100 e 100")


def _validate_direction(direction):
    _validate_int(direction, "direction")
    if direction not in (0, 1):
        raise ValueError("direction deve ser 0 (horario) ou 1 (anti-horario)")


class LEGOEducationMotor:
    """Conecta a um motor LEGO Education e controla uma ou duas saídas."""

    def __init__(self, card_serial=CARD_SERIAL, scan_ms=SCAN_DURATION_MS):
        _validate_int(scan_ms, "scan_ms")
        if scan_ms <= 0:
            raise ValueError("scan_ms deve ser maior que zero")
        if card_serial is not None:
            card_serial_value = int(str(card_serial))
            if card_serial_value < 0 or card_serial_value > 9999:
                raise ValueError("card_serial deve estar entre 0000 e 9999")
        self.card_serial = card_serial
        self.scan_ms = scan_ms
        self.connection = None
        self.write_characteristic = None
        self.notify_characteristic = None
        self.product_id = None
        self.device_serial = None
        self._active_motors = set()

    @property
    def connected(self):
        return self.connection is not None and self.connection.is_connected()

    async def _find_motor(self):
        expected_serial = None
        if self.card_serial is not None:
            expected_serial = int(str(self.card_serial))

        async with aioble.scan(
            duration_ms=self.scan_ms,
            interval_us=30000,
            window_us=30000,
            active=True,
        ) as scanner:
            async for result in scanner:
                if (
                    not result.connectable
                    or ADVERTISEMENT_SERVICE_UUID not in result.services()
                ):
                    continue

                for company_id, data in result.manufacturer(LEGO_COMPANY_ID):
                    if company_id != LEGO_COMPANY_ID or len(data) < 5:
                        continue

                    product_id = (data[0] << 8) | data[1]
                    serial = data[3] | (data[4] << 8)
                    if product_id not in (PRODUCT_SINGLE_MOTOR, PRODUCT_DOUBLE_MOTOR):
                        continue
                    if expected_serial is not None and serial != expected_serial:
                        continue
                    return result.device, product_id, serial

        raise OSError(
            "Nenhum motor LEGO Education compatível foi encontrado "
            "para o Connection Card {!r}".format(self.card_serial)
        )

    async def connect(self):
        if self.connected:
            return

        device, product_id, serial = await self._find_motor()
        self.product_id = product_id
        self.device_serial = "{:04d}".format(serial)

        try:
            self.connection = await device.connect(timeout_ms=10000)
            service = await self.connection.service(SERVICE_UUID)
            if service is None:
                raise OSError("Serviço BLE LEGO FD02 não encontrado")

            self.write_characteristic = await service.characteristic(WRITE_UUID)
            self.notify_characteristic = await service.characteristic(NOTIFY_UUID)
            if self.write_characteristic is None or self.notify_characteristic is None:
                raise OSError("Características BLE de escrita/notificação não encontradas")

            await self.notify_characteristic.subscribe(notify=True)
            info = await self._rpc(bytes((INFO_REQUEST,)), INFO_RESPONSE)
            if len(info) < 17:
                raise OSError("Resposta de identificação LEGO incompleta")

            reported_product = struct.unpack_from("<H", info, 15)[0]
            if reported_product != self.product_id:
                raise OSError(
                    "Produto anunciado e produto informado pelo motor não coincidem"
                )
        except Exception:
            connection = self.connection
            self._clear_connection()
            if connection is not None and connection.is_connected():
                try:
                    await connection.disconnect()
                except Exception as cleanup_error:
                    print("Falha ao fechar BLE após erro: {}".format(cleanup_error))
            raise

    async def _rpc(self, packet, expected_response, motor_mask=None):
        if not self.connected or self.write_characteristic is None:
            raise OSError("Motor não está conectado")

        await self.write_characteristic.write(packet, response=True)
        while True:
            response = await self.notify_characteristic.notified(
                timeout_ms=RESPONSE_TIMEOUT_MS
            )
            if not response:
                continue
            message_id = response[0]
            if message_id == ERROR_REPORT_RESPONSE:
                raise OSError(
                    "Motor LEGO reportou erro RPC: {}".format(response.hex())
                )
            if message_id != expected_response:
                continue

            if motor_mask is not None:
                if len(response) < 3 or response[1] != motor_mask:
                    raise OSError("Resposta RPC inválida para a saída do motor")
                if response[2] != 0:
                    raise OSError(
                        "Comando RPC recusado pelo motor (status {})".format(
                            response[2]
                        )
                    )
            return response

    def _motor_mask(self, motor):
        _validate_int(motor, "motor")
        if self.product_id == PRODUCT_SINGLE_MOTOR:
            if motor != 0:
                raise ValueError("Single Motor aceita somente motor=0")
            return 1
        if self.product_id == PRODUCT_DOUBLE_MOTOR:
            if motor not in (0, 1):
                raise ValueError("Double Motor aceita motor=0 ou motor=1")
            return 1 << motor
        raise OSError("Produto LEGO desconhecido; chame connect() primeiro")

    async def run(self, speed=25, direction=0, motor=0):
        """Inicia rotação contínua; chame stop() ou disconnect() para parar."""
        _validate_speed(speed)
        _validate_direction(direction)
        motor_mask = self._motor_mask(motor)

        for active_motor in tuple(self._active_motors):
            if active_motor != motor:
                await self.stop(motor=active_motor)
        await self._rpc(
            struct.pack("<BBb", MOTOR_SET_SPEED, motor_mask, speed),
            MOTOR_SET_SPEED_RESULT,
            motor_mask,
        )
        self._active_motors.add(motor)
        await self._rpc(
            struct.pack("<BBB", MOTOR_RUN, motor_mask, direction),
            MOTOR_RUN_RESULT,
            motor_mask,
        )

    async def run_tank(self, speed_left, speed_right):
        """Run Double Motor outputs 0 and 1 concurrently using signed speeds."""
        _validate_speed(speed_left)
        _validate_speed(speed_right)
        left_mask = self._motor_mask(0)
        right_mask = self._motor_mask(1)

        for motor_mask, speed in (
            (left_mask, speed_left),
            (right_mask, speed_right),
        ):
            await self._rpc(
                struct.pack("<BBb", MOTOR_SET_SPEED, motor_mask, abs(speed)),
                MOTOR_SET_SPEED_RESULT,
                motor_mask,
            )

        for motor, motor_mask, speed in (
            (0, left_mask, speed_left),
            (1, right_mask, speed_right),
        ):
            self._active_motors.add(motor)
            direction = 0 if speed >= 0 else 1
            await self._rpc(
                struct.pack("<BBB", MOTOR_RUN, motor_mask, direction),
                MOTOR_RUN_RESULT,
                motor_mask,
            )

    async def run_for_time(self, time_ms, speed=25, direction=0, motor=0):
        """Gira por time_ms milissegundos e aguarda o término."""
        _validate_int(time_ms, "time_ms")
        if time_ms < 0 or time_ms > 0xFFFFFFFF:
            raise ValueError("time_ms deve estar entre 0 e 4294967295")
        _validate_speed(speed)
        _validate_direction(direction)
        motor_mask = self._motor_mask(motor)

        for active_motor in tuple(self._active_motors):
            if active_motor != motor:
                await self.stop(motor=active_motor)
        await self._rpc(
            struct.pack("<BBb", MOTOR_SET_SPEED, motor_mask, speed),
            MOTOR_SET_SPEED_RESULT,
            motor_mask,
        )
        self._active_motors.add(motor)
        await self._rpc(
            struct.pack("<BBIB", MOTOR_RUN_FOR_TIME, motor_mask, time_ms, direction),
            MOTOR_RUN_FOR_TIME_RESULT,
            motor_mask,
        )
        self._active_motors.discard(motor)

    async def stop(self, motor=0):
        """Para uma saída do motor."""
        motor_mask = self._motor_mask(motor)
        await self._rpc(
            struct.pack("<BB", MOTOR_STOP, motor_mask),
            MOTOR_STOP_RESULT,
            motor_mask,
        )
        self._active_motors.discard(motor)

    async def disconnect(self):
        """Tenta parar as saídas ativas e encerra a conexão BLE."""
        connection = self.connection
        if connection is None:
            return

        try:
            if self.connected:
                for motor in tuple(self._active_motors):
                    await self.stop(motor=motor)
        finally:
            try:
                if connection.is_connected():
                    await connection.disconnect()
            finally:
                self._clear_connection()

    def _clear_connection(self):
        self.connection = None
        self.write_characteristic = None
        self.notify_characteristic = None
        self.product_id = None
        self.device_serial = None
        self._active_motors.clear()
