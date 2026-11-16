# Cibersegurança com robótica (ESP-NOW + LEGO)

Material didático que ensina os três princípios da segurança — **Confidencialidade, Integridade e Disponibilidade (CIA)** — usando um canal de rádio propositalmente inseguro entre microcontroladores **ESP32** e um **motor LEGO Education** como atuador físico do "robô". A ideia pedagógica: os alunos **quebram** o canal (escutam, repetem, injetam) antes de **defendê-lo**.

## Arquitetura (sem computador no meio)

```
[controle M5 + 2 botões] --ESP-NOW--> [robô M5] --BLE--> [motor LEGO]
                                ^
                         [espião M5] escuta tudo e pode repetir (replay)
```

O motor LEGO é acionado **direto do ESP32 por BLE** (porte reduzido da biblioteca oficial `legoeducation` para MicroPython, em [`micropython/robo/lego_motor.py`](micropython/robo/lego_motor.py)). Não há PC nem ponte serial.

## Três experimentos = três conceitos

| Etapa | Canal | Ataque | Conceito |
|-------|-------|--------|----------|
| 1. **Broadcast** (texto claro) | todos ouvem todos | o espião lê e envia comandos → assume o robô | confidencialidade: sem endereço, sem segredo |
| 2. **Unicast** (texto claro) | endereçado ao MAC do robô | o espião comum não vê; mas um sniffer em **modo monitor** captura | "endereçar não é cifrar" |
| 3. **Unicast + AES-128** | comando cifrado | o espião não lê o comando, mas ainda **repete** (replay) o pacote | "cifrar não é autenticar" |

Próxima versão (defesa): **HMAC + número de sequência/nonce** contra replay.

## Estrutura

```
ciberseguranca-robotica/
├── INSTALACAO.md                 # guia completo: hardware, firmwares, VS Code, gravação
├── micropython/
│   ├── controle/                 # roda no M5Stamp S3 (2 botões)
│   │   ├── controle.py              # broadcast, texto claro
│   │   ├── controle_unicast.py      # unicast, texto claro
│   │   └── controle_cripto.py       # unicast + AES-128
│   ├── robo/                     # roda no M5Stack Capsule (fala BLE com o motor)
│   │   ├── lego_motor.py            # driver BLE do motor LEGO (scan + RPC)
│   │   ├── robo.py                  # recebe F/T/E/D/P e move o motor
│   │   └── robo_cripto.py           # decifra o bloco AES e move
│   └── espiao/                   # roda no M5StickC PlusSE (tela + 2 botões)
│       ├── espiao.py                # captura broadcast e faz replay
│       └── espiao_cripto.py         # mostra a cifra em hex e repete os bytes
```

> O espião em **modo monitor** (promíscuo), que captura unicast e a cifra pelo ar, é um sketch Arduino/C (o MicroPython não expõe `esp_wifi_set_promiscuous`). Ele e o guia de estudo serão adicionados em `arduino/` e `docs/` — ver referências no `INSTALACAO.md`.

## Como começar

Leia o [`INSTALACAO.md`](INSTALACAO.md): montar do zero num VS Code novo, instalar `mpremote`/`arduino-cli`, gravar cada placa e trocar entre os três experimentos. Convenções que precisam bater entre as placas (canal, chave AES, MAC do robô, Connection Card) estão resumidas lá.

## Hardware

- Controle: **M5Stamp S3** + Breakout v2 + 2 botões
- Robô: **M5Stack Capsule** (ESP32-S3, UiFlow2)
- Espião: **M5StickC PlusSE** (UiFlow2) — e, opcional, **Seeed XIAO ESP32-C6** para o modo monitor
- Atuador: **LEGO Education Double Motor** + Connection Card

---

Projeto IFRS Campus Porto Alegre (POALab) × Tufts/CEEO — mobilidade nov/2026.
