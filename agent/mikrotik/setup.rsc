# ==============================================================================
# Trilan NVR Backup Automation — Provisionamento de rede/firewall no RouterOS v7
# ==============================================================================
# Uso: execute este script no terminal do MikroTik (ou via /import setup.rsc)
# após criar a bridge `br-trilan` (172.30.250.1/30) e a interface `veth-trilan`
# (172.30.250.2/30).
#
# O script é idempotente: pode ser executado mais de uma vez sem duplicar regras
# e sem sobrescrever IPs já liberados em `/ip service ssh`.
# ==============================================================================

:local bridgeTrilan "br-trilan"
:local redeTrilan "172.30.250.0/30"

# 1. Libera SSH (TCP/22) vindo da bridge do container antes do primeiro drop do input
:if ([:len [/ip firewall filter find comment="TRILAN-SSH-ANTENAS"]] = 0) do={
    :local dropInput [/ip firewall filter find chain=input action=drop disabled=no]
    :if ([:len $dropInput] > 0) do={
        /ip firewall filter add chain=input action=accept protocol=tcp in-interface=$bridgeTrilan dst-port=22 place-before=($dropInput->0) comment="TRILAN-SSH-ANTENAS"
    } else={
        /ip firewall filter add chain=input action=accept protocol=tcp in-interface=$bridgeTrilan dst-port=22 comment="TRILAN-SSH-ANTENAS"
    }
}

# 2. Adiciona 172.30.250.0/30 ao AVAILABLE-FROM do SSH caso haja restrição configurada
:local sshItem [/ip service find name=ssh]
:if ([:len $sshItem] > 0) do={
    :local sshAddrs [/ip service get $sshItem address]
    :if ([:len $sshAddrs] > 0) do={
        :if ([:typeof [:find $sshAddrs $redeTrilan]] = "nil") do={
            /ip service set $sshItem address=($sshAddrs . "," . $redeTrilan)
        }
    }
}

# 3. Libera encaminhamento (forward) da bridge do container para alcançar antenas/equipamentos
:if ([:len [/ip firewall filter find comment="TRILAN-FORWARD-CONTAINER"]] = 0) do={
    :local dropFwd [/ip firewall filter find chain=forward action=drop disabled=no]
    :if ([:len $dropFwd] > 0) do={
        /ip firewall filter add chain=forward action=accept in-interface=$bridgeTrilan place-before=($dropFwd->0) comment="TRILAN-FORWARD-CONTAINER"
    } else={
        /ip firewall filter add chain=forward action=accept in-interface=$bridgeTrilan comment="TRILAN-FORWARD-CONTAINER"
    }
}

# 4. Garante NAT (masquerade) para o tráfego originado na sub-rede do container
:if ([:len [/ip firewall nat find comment="TRILAN-NAT-CONTAINER"]] = 0) do={
    /ip firewall nat add chain=srcnat action=masquerade src-address=$redeTrilan comment="TRILAN-NAT-CONTAINER"
}

:put "Regras Trilan aplicadas com sucesso."
