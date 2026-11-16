# descobre_pinos.py - mostra qual GPIO muda quando voce aperta um botao.
# Use no Stamp S3 do controle para preencher PINO_FRENTE e PINO_TRAS.
#
#   mpremote connect <porta-controle> run micropython/ferramentas/descobre_pinos.py
#
# Aperte e solte cada botao: aparece "GPIOx: 1 -> 0" (botao no GND, ATIVO_EM=0)
# ou "GPIOx: 0 -> 1" (botao no 3V3, ATIVO_EM=1). Ctrl+C encerra.
#
# Fica de fora: 19/20 (USB - mexer derruba a serial) e 26..37 (memoria flash).

from machine import Pin
import time

CANDIDATOS = list(range(0, 19)) + list(range(38, 49))

pinos = {}
for n in CANDIDATOS:
    try:
        pinos[n] = Pin(n, Pin.IN, Pin.PULL_UP)
    except Exception:
        pass

estado = {n: p.value() for n, p in pinos.items()}
print("Vigiando GPIOs:", sorted(pinos))
print("Aperte cada botao...")

while True:
    for n, p in pinos.items():
        v = p.value()
        if v != estado[n]:
            print("GPIO%d: %d -> %d" % (n, estado[n], v))
            estado[n] = v
    time.sleep_ms(20)
