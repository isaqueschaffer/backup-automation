"""Agente Linux (Mikrotik, 1.1.58): as rotinas do serviço Windows que faltavam no service_linux.py (coletas,
alarmes, vigia de backup travado; ponte: sem webhooks nem ciclo da noite), sem rede."""
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import service_linux  # noqa: E402
from src.application import estado  # noqa: E402


def _esperas(*respostas):
    """STOP.wait falso: devolve as respostas em ordem e liga o STOP de verdade na que for True."""
    fila = list(respostas)

    def wait(_s=None):
        r = fila.pop(0)
        if r:
            service_linux.STOP.set()
        return r
    return wait


class TestRotinasLinux(unittest.TestCase):
    def tearDown(self):
        service_linux.STOP.clear()
        estado.backup_em_andamento, estado.backup_inicio = False, None

    def test_backup_marca_o_estado_compartilhado(self):
        visto = []
        with mock.patch("src.backup.tunel.executar_backup_tunel", side_effect=lambda t: visto.append(
                    estado.backup_em_andamento)), \
                mock.patch("src.application.backup_job.run_backup") as em_disco:
            service_linux.run_backup("manual_dashboard")
        self.assertEqual(visto, [True])
        em_disco.assert_not_called()   # o backup comum grava em disco: nunca no Mikrotik
        self.assertFalse(estado.backup_em_andamento)

    def test_ping_declara_comando_alarme_e_dispara_a_tarefa(self):
        tarefa = {"acao": "armar", "central_id": 1, "equipamento": "DEF"}
        recebidas = []

        def ping(conf, recursos_extra=()):
            self.assertIn("comando_alarme", recursos_extra)
            service_linux.STOP.set()
            return {"alarme_task": tarefa}

        with mock.patch.object(service_linux, "ping_server", side_effect=ping), \
                mock.patch.object(service_linux, "run_alarm_command", side_effect=lambda c, t: recebidas.append(t)):
            service_linux.heartbeat({}, threading.Event())
            time.sleep(0.2)
        self.assertEqual(recebidas, [tarefa])

    def test_reinicio_com_backup_em_andamento_e_forcado(self):
        estado.backup_em_andamento = True
        with mock.patch.object(service_linux, "ping_server", return_value={"restart": True}), \
                mock.patch.object(service_linux, "reinicio_forcado", side_effect=SystemExit) as forcado:
            with self.assertRaises(SystemExit):
                service_linux.heartbeat({}, threading.Event())
        forcado.assert_called_once()

    def test_vigia_derruba_backup_acima_do_limite(self):
        estado.backup_em_andamento = True
        estado.backup_inicio = time.monotonic() - service_linux.LIMITE_BACKUP_S - 60
        with mock.patch.object(service_linux.STOP, "wait", side_effect=[False, True]), \
                mock.patch.object(service_linux, "reinicio_forcado") as forcado:
            service_linux.vigia_backup_loop({})
        forcado.assert_called_once()

    def test_ciclo_envia_o_coletado_e_pula_durante_backup(self):
        enviados = []
        with mock.patch.object(service_linux, "_equipamentos", return_value=[{"tipo": "NVR"}]), \
                mock.patch.object(service_linux.STOP, "wait", side_effect=_esperas(False, True)):
            service_linux.ciclo_loop({}, "teste", 0, 1, lambda eqs: [{"n": len(eqs)}],
                                     lambda c, l: enviados.append(l))
        self.assertEqual(enviados, [[{"n": 1}]])
        estado.backup_em_andamento = True
        service_linux.STOP.clear()
        with mock.patch.object(service_linux, "_equipamentos", return_value=[{"tipo": "NVR"}]), \
                mock.patch.object(service_linux.STOP, "wait", side_effect=_esperas(False, True)):
            service_linux.ciclo_loop({}, "teste", 0, 1, lambda eqs: [1], lambda c, l: enviados.append(l), True)
        self.assertEqual(len(enviados), 1)

    def test_ponte_nao_liga_webhooks_nem_ciclo_da_noite(self):
        self.assertFalse(hasattr(service_linux, "iniciar_webhooks"))
        threads = []
        with mock.patch.dict("os.environ", {}, clear=False) as env,                 mock.patch.object(service_linux.threading, "Thread",
                                  side_effect=lambda target=None, **k: threads.append(target) or mock.MagicMock()),                 mock.patch.object(service_linux, "load_conf", return_value={"server_url": "https://s"}),                 mock.patch.object(service_linux.log_remoto, "instalar"),                 mock.patch.object(service_linux, "schedule", return_value=(2, 0)),                 mock.patch.object(service_linux, "iniciar_coletas"),                 mock.patch.object(service_linux, "enviar_logs_restantes"),                 mock.patch.object(service_linux.signal, "signal"):
            env.pop("TRILAN_NOITE_AUTOMATICA", None)
            service_linux.STOP.set()
            service_linux.main()
        self.assertNotIn(service_linux.noite_loop, threads)
        self.assertIn(service_linux.heartbeat, threads)


if __name__ == "__main__":
    unittest.main()
