#!/usr/bin/env python3
"""prepara_equipe.py - prepara as 2 varinhas (robo + controle) de UMA equipe da corrida.

Roda NO COMPUTADOR (nao na placa). Com as duas varinhas da equipe na USB:
  1. le o MAC do robo e do controle;
  2. escolhe o canal da equipe (1 -> 1, 2 -> 6, 3 -> 11) e a chave AES
     (equipe 1 mantem a chave atual; as outras ganham uma aleatoria, guardada em
     pc/equipes.json para nao mudar se rodar de novo);
  3. grava /lib/equipe.py nas duas varinhas, o main.py de cada uma, e reinicia.

Uso (na raiz do projeto):
  python3 pc/prepara_equipe.py --equipe 2 --motor 1234 \\
      --robo /dev/cu.usbmodem101 --controle /dev/cu.usbmodem1101

Sem --robo/--controle, o script lista as portas usbmodem com o MAC de cada uma,
para voce escolher.
"""
import argparse
import glob
import json
import os
import secrets
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQ_EQUIPES = os.path.join(RAIZ, "pc", "equipes.json")

CANAIS = {1: 1, 2: 6, 3: 11}
CORES = {1: (0, 0, 30), 2: (0, 30, 0), 3: (30, 12, 0)}   # azul, verde, laranja
CHAVE_EQUIPE_1 = b"ciberseg-aes-key"

LE_MAC = ("import network;w=network.WLAN(network.STA_IF);w.active(True);"
          "print(':'.join('%02x'%b for b in w.config('mac')))")


def mpremote(porta, *args, capturar=False):
    cmd = ["mpremote", "connect", porta, *args]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        sys.exit("error in %s:\n%s%s" % (" ".join(cmd), r.stdout, r.stderr))
    return r.stdout.strip() if capturar else None


def le_mac(porta):
    return mpremote(porta, "exec", LE_MAC, capturar=True).splitlines()[-1]


def carrega_equipes():
    try:
        with open(ARQ_EQUIPES) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--equipe", type=int, required=True, choices=sorted(CANAIS))
    ap.add_argument("--motor", required=True, help="LEGO motor Connection Card number")
    ap.add_argument("--robo", help="ROBOT wand port")
    ap.add_argument("--controle", help="CONTROLLER wand port")
    a = ap.parse_args()

    if not (a.robo and a.controle):
        print("Ports found (MAC of each):")
        for p in sorted(glob.glob("/dev/cu.usbmodem*")):
            try:
                print("  %s  %s" % (p, le_mac(p)))
            except SystemExit:
                print("  %s  (busy or not MicroPython)" % p)
        sys.exit("Pass --robo and --controle.")

    mac_robo, mac_ctl = le_mac(a.robo), le_mac(a.controle)
    equipes = carrega_equipes()
    chave_ant = equipes.get(str(a.equipe), {}).get("chave_hex")
    if a.equipe == 1:
        chave = CHAVE_EQUIPE_1
    elif chave_ant:
        chave = bytes.fromhex(chave_ant)
    else:
        chave = secrets.token_bytes(16)

    canal = CANAIS[a.equipe]
    robo_bytes = bytes(int(x, 16) for x in mac_robo.split(":"))
    conteudo = (
        "# equipe.py - gerado por pc/prepara_equipe.py. NAO edite a mao.\n"
        "EQUIPE = %d\n"
        "CANAL = %d\n"
        "ROBO_MAC = %r   # %s\n"
        "CHAVE = %r\n"
        "CARD_SERIAL = %r\n"
        "COR_EQUIPE = %r\n"
    ) % (a.equipe, canal, robo_bytes, mac_robo, chave, a.motor, CORES[a.equipe])

    tmp = os.path.join(RAIZ, "pc", "_equipe_tmp.py")
    with open(tmp, "w") as f:
        f.write(conteudo)
    try:
        for porta, main_py in ((a.controle, "micropython/controle/controle_nfc.py"),
                               (a.robo, "micropython/robo/robo_modos.py")):
            mpremote(porta, "fs", "cp", tmp, ":/lib/equipe.py",
                     "+", "fs", "cp", os.path.join(RAIZ, main_py), ":/main.py",
                     "+", "reset")
    finally:
        os.remove(tmp)

    equipes[str(a.equipe)] = {"canal": canal, "robo_mac": mac_robo, "controle_mac": mac_ctl,
                              "motor": a.motor, "chave_hex": chave.hex()}
    with open(ARQ_EQUIPES, "w") as f:
        json.dump(equipes, f, indent=2, sort_keys=True)

    print("Team %d ready: channel %d, robot %s, controller %s, motor %s"
          % (a.equipe, canal, mac_robo, mac_ctl, a.motor))
    print("AES key: %s (saved in pc/equipes.json)" % chave.hex())


if __name__ == "__main__":
    main()
