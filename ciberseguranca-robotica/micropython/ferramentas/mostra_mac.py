# mostra_mac.py - imprime o MAC STA da placa (o endereco usado pelo ESP-NOW).
#
# Use no ROBO para descobrir o ROBO_MAC que vai no controle_unicast.py:
#   mpremote connect <porta-robo> run micropython/ferramentas/mostra_mac.py
#
# Copie a linha "ROBO_MAC = ..." para o topo do controle_unicast.py.

import network

sta = network.WLAN(network.STA_IF)
sta.active(True)
mac = sta.config('mac')

print("MAC (humano):", ':'.join('%02x' % x for x in mac))
print("Cole no controle_unicast.py:")
print("ROBO_MAC = b'" + ''.join('\\x%02x' % x for x in mac) + "'")
