"""
Módulo Legado: Receptor de Traps SNMP do Digifort (Porta 162 UDP)
==================================================================
NOTA HISTÓRICA:
Este método foi utilizado nas primeiras versões da automação para monitorar
o status online/offline das câmeras do Digifort recebendo traps SNMP enviadas
pelo próprio software Digifort na porta UDP 162.

OIDs conhecidos do Digifort:
- .1.3.6.1.4.1.33655.1.1.100.2.4 (...\\x64\\x02\\x04): Falha de Comunicação da Câmera (Offline)
- .1.3.6.1.4.1.33655.1.1.100.2.5 (...\\x64\\x02\\x05): Câmera Restaurada (Online)

MOTIVO DA SUBSTITUIÇÃO:
O método baseado em SNMP exigia configuração de traps no Digifort, dependia
da abertura da porta 162 UDP (frequentemente em conflito com o serviço SNMP
Trap nativo do Windows ou outros utilitários) e não garantia checagem ativa
quando o serviço era reiniciado.
Foi substituído pela verificação ativa via Ping ICMP concorrente executado
diretamente pelo Agente Windows em 'agent/src/application/webhook_digifort.py'.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from archive.legacy_scripts.digifort_snmp import *

if __name__ == '__main__':
    rodar_sniffer_snmp()
