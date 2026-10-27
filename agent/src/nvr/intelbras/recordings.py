import logging
import re
import requests
from datetime import datetime
from requests.auth import HTTPDigestAuth

TIMEOUT_S = 5


def tem_gravacao_no_dia(nvr_ip, usuario, senha, canal_id, data_ref: datetime) -> bool:
    """
    Verifica se há gravações em um determinado dia para um canal de NVR/DVR Intelbras.
    Utiliza a API Dahua mediaFileFind.cgi.
    canal_id: int ou str representando o número do canal (1-indexed).
    """
    auth = HTTPDigestAuth(usuario, senha)
    try:
        ch_num = int(str(canal_id).strip())
    except (ValueError, TypeError):
        ch_num = 1

    dt_str = data_ref.strftime("%Y-%m-%d")
    token = None

    try:
        # 1. Cria a sessão de busca
        r_create = requests.get(
            f"http://{nvr_ip}/cgi-bin/mediaFileFind.cgi?action=factory.create",
            auth=auth,
            timeout=TIMEOUT_S,
            verify=False
        )
        if r_create.status_code != 200 or "=" not in r_create.text:
            return False

        token = r_create.text.strip().split("=")[1].strip()

        # 2. Executa a busca pelo canal e data
        params = {
            "action": "findFile",
            "object": token,
            "condition.Channel": ch_num,
            "condition.StartTime": f"{dt_str} 00:00:00",
            "condition.EndTime": f"{dt_str} 23:59:59",
            "condition.Flags[0]": "Timing",
            "condition.Flags[1]": "Manual",
            "condition.Flags[2]": "Event",
        }
        r_find = requests.get(
            f"http://{nvr_ip}/cgi-bin/mediaFileFind.cgi",
            params=params,
            auth=auth,
            timeout=TIMEOUT_S,
            verify=False
        )

        has_rec = False
        if r_find.status_code == 200 and "OK" in r_find.text:
            # 3. Consulta se há arquivos
            r_next = requests.get(
                f"http://{nvr_ip}/cgi-bin/mediaFileFind.cgi?action=findNextFile&object={token}&count=1",
                auth=auth,
                timeout=TIMEOUT_S,
                verify=False
            )
            if r_next.status_code == 200:
                m = re.search(r"found=(\d+)", r_next.text)
                if m and int(m.group(1)) > 0:
                    has_rec = True

        return has_rec
    except Exception as e:
        logging.debug(f"Erro ao verificar gravacao Intelbras canal {ch_num} dia {dt_str}: {e}")
        return False
    finally:
        # 4. Destrói a sessão de busca para liberar memória no NVR
        if token:
            try:
                requests.get(
                    f"http://{nvr_ip}/cgi-bin/mediaFileFind.cgi?action=destroy&object={token}",
                    auth=auth,
                    timeout=3,
                    verify=False
                )
            except Exception:
                pass
