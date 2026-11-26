# 📊 Guia: Dados para o Dashboard KPI - FiberHome OLT

## ✅ Situação dos Dados

Todos os dados necessários **já são coletados pelo template** `Cloud - FiberHome 2.0`.
Não é necessário criar nenhum novo item no Zabbix. Basta criar as queries corretas no Grafana.

---

## 1. KPIs Globais de ONU (Painel de Números)

Esses são itens simples, com um valor numérico cada. No Grafana, use o painel **Stat** ou **Big Number**.

| KPI | Chave Zabbix (Item Key) | Tipo |
|---|---|---|
| Total de ONUs | `onuCount` | SNMP |
| ONUs Online | `onu.online` | Dependent |
| ONUs Offline | `onu.offline` | Dependent |
| ONUs com Falha | `onu.falha` | Dependent |
| ONUs sem Energia | `onu.energia` | Dependent |

### Como configurar no Grafana (Query):
- **Data Source**: Zabbix
- **Group**: seu grupo de hosts (ex: `OLTs`)
- **Host**: nome da sua OLT (ex: `OLT FiberHome`)
- **Application**: `TOTAIS ONUs`
- **Item**: Selecione o item desejado (ex: `ONUs ONLINE`)

> Os itens `onu.online`, `onu.offline`, `onu.falha` e `onu.energia` são **Dependentes** do item mestre `qtd.onu`. Eles só terão dados se o item `QUANTIDADE ONUS` estiver coletando corretamente.

---

## 2. Temperatura da OLT (Painel Gauge ou Stat)

| KPI | Chave Zabbix | OID | Unidade |
|---|---|---|---|
| Temperatura do Chassis | `Temp` | `1.3.6.1.4.1.5875.800.3.9.4.5.0` | °C |
| Temperatura do GBIC por PON | `oltPonOpticalTemperature.[{#SNMPINDEX}]` | `1.3.6.1.4.1.5875.800.3.9.3.4.1.11.X` | ºC |

> **Atenção**: A temperatura do GBIC usa multiplicador `0.01`, então o valor `4800` no SNMP = `48°C`.

---

## 3. Potência TX por Porta PON (Gráfico de Linhas)

| KPI | Chave Zabbix | OID | Unidade |
|---|---|---|---|
| Potência TX PON | `oltPonTxOpticalPower.[{#SNMPINDEX}]` | `.1.3.6.1.4.1.5875.800.3.9.3.4.1.8.X` | dBm |

> Multiplicador `0.01` aplicado. Um valor SNMP de `-300` = `-3.00 dBm`.
> No Grafana, faça uma query com **Application** = `POTENCIA_PON` e selecione todas as interfaces com `.*`.

---

## 4. ONUs Online vs Autorizadas por PON (Gráfico de Barras Agrupado)

| Dado | Chave Zabbix | Application |
|---|---|---|
| ONUs Online por PON | `GEPON-OLT-COMMON-MIB[onuStatus=1,{#OLTPONNAME}]` | `ONLINE_PON` |
| ONUs Offline por PON | `GEPON-OLT-COMMON-MIB[onuStatus!=1,{#OLTPONNAME}]` | `OFFLINE_PON` |
| ONUs Autorizadas por PON | `GEPON-OLT-COMMON-MIB.oltPonAuthOnuNum.[{#SNMPINDEX}]` | `AUTENTICADAS_PON` |

### Como configurar no Grafana:
- Crie **3 queries** (A, B, C) no mesmo painel
- Cada query usa o mesmo Host, mas com **Item** diferente
- Mude o **Alias** de cada query para `Online`, `Offline`, `Autorizadas`
- Use o painel **Bar Chart** com modo `Grouped`

---

## 5. Tráfego por Porta PON - bps Entrada/Saída (Gráfico de Área)

| Dado | Chave Zabbix | Application |
|---|---|---|
| Tráfego Entrada (bps) | `net.if.in[ifHCInOctets.{#SNMPINDEX}]` | `Network` |
| Tráfego Saída (bps) | `net.if.out[ifHCOutOctets.{#SNMPINDEX}]` | `Network` |

> O template já aplica `× 8` (converte bytes para bits) e `CHANGE_PER_SECOND` (taxa por segundo).
> No Grafana, selecione **Application** = `Network` e use `.*` no item para pegar todas as portas.

---

## 6. Tráfego por Interface XFP/SFP (Gráfico de Área)

| Dado | Chave Zabbix | Application |
|---|---|---|
| Entrada XFP/SFP | `neeet.if.in[ifHCInOctets.{#SNMPINDEX}]` | `Network` |
| Saída XFP/SFP | `neeet.if.out[ifHCOutOctets.{#SNMPINDEX}]` | `Network` |

> **Importante**: As chaves XFP/SFP usam `neeet` (com 3 e's) - é o nome exato no template.

---

## 7. CPU e Memória por Card (Gauge ou Time Series)

| Dado | Chave Zabbix | Application |
|---|---|---|
| CPU por Card | `cardCpuUtil[{#CARD}]` | `CPU por Card` |
| Memória por Card | `cardMenUtil[{#CARD}]` | `Memoria por Card` |

> Coletados a cada 60 segundos. Multiplicador `0.01` aplicado.
> Funciona apenas para cards do tipo `GC8B (527)` ou `GCOB (550)`.

---

## 8. Sinal RX por ONU (Time Series - Histórico)

| Dado | Chave Zabbix | Application |
|---|---|---|
| Sinal RX ONU (dBm) | `fiberhome_optical.py["{HOST.IP}",...]` | `ONU` |

> Este item é coletado a cada **5 minutos** via script Python/Telnet.
> No Grafana, use **Application** = `ONU` e o campo Item com o nome da ONU desejada.

---

## 🗺️ Estrutura Sugerida do Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│  ROW 1: KPIs Gerais                                         │
│  [Total ONUs] [Online] [Offline] [Falha] [Temp. Chassis]   │
├─────────────────────────────────────────────────────────────┤
│  ROW 2: Por PON                                             │
│  [Online vs Autorizadas por PON - Bar Chart]                │
│  [Potência TX por PON - Gauge ou Time Series]               │
├─────────────────────────────────────────────────────────────┤
│  ROW 3: Tráfego                                             │
│  [Tráfego PON IN/OUT - Time Series]                         │
│  [Tráfego XFP/SFP IN/OUT - Time Series]                    │
├─────────────────────────────────────────────────────────────┤
│  ROW 4: Hardware                                            │
│  [CPU por Card] [Memória por Card] [Temp. GBIC por PON]    │
├─────────────────────────────────────────────────────────────┤
│  ROW 5: Inventário                                          │
│  [Inventário ONUs - Business Text (Grid de Cards)]          │
└─────────────────────────────────────────────────────────────┘
```

---

## ⚠️ Pré-requisitos para os Dados Aparecerem

1. **Template aplicado** ao host da OLT no Zabbix
2. **Macros configuradas**: `{$GEPON_USER}`, `{$GEPON_PASS}`, `{$GEPON_ENABLE}`, `{$DB_HOST}`, `{$SNMP_COMMUNITY}`
3. **Scripts Python** no diretório `externalscripts` do Zabbix:
   - `fiberhome_onu_discovery_name.py`
   - `fiberhome_optical.py`
4. **Plugin Zabbix** instalado no Grafana
5. **SNMP habilitado** na OLT com a community correta
