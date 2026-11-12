"""Coleta periodica dos alarmes das centrais Intelbras cadastradas nos equipamentos DEFENSE (Intelbras Defense
IA), pela API HTTP de alarmes (porta configuravel em `config_extra.porta_alarme`, padrao 3001)."""
import logging
import time
from typing import Any, Dict, List

INTERVALO_ALARMES_S = 300
ESPERA_APOS_COMANDO_S = 8  # a tela /arm-disarm do painel tambem espera ~8s antes de reler o estado da central


def atender_comando_alarme(task: dict, conf: dict, comandar=None, coletar=None, enviar_resultado=None,
                           enviar_status=None, esperar=time.sleep) -> bool:
    """Executa o armar/desarmar pedido pelo painel (`alarme_task` do ping), devolve o resultado ao servidor e, se deu
    certo, reenvia o status das centrais desse DEFENSE. Nunca levanta erro. Dependencias injetaveis para teste."""
    from src.application.api_client import send_resultado_comando_alarme, send_status_alarmes
    from src.vms.defense_alarmes import coletar_alarmes_equipamento, comandar_central
    comandar = comandar or comandar_central
    coletar = coletar or coletar_alarmes_equipamento
    enviar_resultado = enviar_resultado or send_resultado_comando_alarme
    enviar_status = enviar_status or send_status_alarmes

    acao = task.get("acao")
    try:
        mensagem = comandar(task.get("ip"), task.get("username"), task.get("password"), int(task.get("porta") or 3001),
                            str(task.get("central_id")), acao)
        sucesso = True
    except Exception as e:
        logging.warning(f"  [DEFENSE] Falha no comando {acao} da central {task.get('central_id')}: {e}")
        mensagem, sucesso = str(e) or e.__class__.__name__, False
    enviar_resultado(conf, sucesso, mensagem)

    if sucesso:
        esperar(ESPERA_APOS_COMANDO_S)
        equipamento = {
            "name": task.get("equipamento"), "tipo": "DEFENSE", "ip": task.get("ip"),
            "username": task.get("username"), "password": task.get("password"),
            "config_extra": {"porta_alarme": task.get("porta")},
        }
        try:
            enviar_status(conf, [{"nome": task.get("equipamento"), **coletar(equipamento)}])
        except Exception as e:
            logging.warning(f"  [DEFENSE] Falha ao reenviar o status dos alarmes apos o comando: {e}")
    return sucesso


def coletar_status_alarmes(equipamentos: list, coletar=None) -> List[Dict[str, Any]]:
    """[{'nome': equipamento, 'ip', 'alarmes': [...] ou 'erro': ...}] dos equipamentos DEFENSE ativos com IP e
    senha cadastrados. `coletar(equipamento)` e injetavel para teste."""
    from src.vms.defense_alarmes import coletar_alarmes_equipamento
    coletar = coletar or coletar_alarmes_equipamento
    resultado = []
    for eq in equipamentos or []:
        try:
            if not eq.get("active", True) or (eq.get("tipo") or "").upper() != "DEFENSE":
                continue
            resultado.append({"nome": eq.get("name"), **coletar(eq)})
        except Exception as e:
            logging.warning(f"Erro ao coletar os alarmes de {eq.get('name')}: {e}", exc_info=True)
    return resultado
