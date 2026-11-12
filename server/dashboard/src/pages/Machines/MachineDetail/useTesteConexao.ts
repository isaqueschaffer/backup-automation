import { useCallback, useEffect, useRef, useState } from "react";
import { iniciarTesteConexao, obterTesteConexao } from "../../../api/client";
import { ConexaoTeste } from "../../../api/types";

const INTERVALO_CONSULTA_MS = 1000;

export function fmtCronometro(seg: number): string {
  const s = Math.max(0, Math.floor(seg));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function erroDaApi(e: unknown): string {
  const detalhe = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detalhe === "string" ? detalhe : "Falha ao falar com o servidor.";
}

// Etapa feita conta 1; a em andamento conta meia, para a barra andar assim que ela começa
export function percentualTeste(t: ConexaoTeste | null): number {
  if (!t || t.etapas.length === 0) return 3;
  if (t.concluido) return 100;
  const feitas = t.etapas.reduce((soma, e) => soma + (e.estado === "andamento" ? 0.5 : e.estado === "pendente" ? 0 : 1), 0);
  return Math.max(3, Math.min(97, (feitas / t.etapas.length) * 100));
}

/** Dispara o "Testar conexão" de um equipamento e acompanha o andamento (consulta a cada 1 s).
 *  `iniciar()` começa (ou repete) o teste; com `automatico` ele começa ao montar. */
export function useTesteConexao(
  machineId: string, eqId: string, opts: { automatico?: boolean; onConcluido?: (t: ConexaoTeste | null) => void } = {},
) {
  const [teste, setTeste] = useState<ConexaoTeste | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [rodada, setRodada] = useState(opts.automatico ? 1 : 0);
  const [inicioMs, setInicioMs] = useState(() => Date.now());
  const [agoraMs, setAgoraMs] = useState(() => Date.now());
  const concluidoRef = useRef(opts.onConcluido);
  concluidoRef.current = opts.onConcluido;

  useEffect(() => {
    if (rodada === 0) return;
    let cancelado = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setTeste(null); setErro(null);
    setInicioMs(Date.now()); setAgoraMs(Date.now());

    const acompanhar = (atual: ConexaoTeste) => {
      if (cancelado) return;
      setTeste(atual);
      if (atual.concluido || !atual.task_id) {
        concluidoRef.current?.(atual);
        return;
      }
      timer = setTimeout(async () => {
        try {
          acompanhar(await obterTesteConexao(machineId, eqId, atual.task_id!));
        } catch (e) {
          if (!cancelado) { setErro(erroDaApi(e)); concluidoRef.current?.(null); }
        }
      }, INTERVALO_CONSULTA_MS);
    };

    iniciarTesteConexao(machineId, eqId).then(acompanhar).catch(e => {
      if (!cancelado) { setErro(erroDaApi(e)); concluidoRef.current?.(null); }
    });
    return () => { cancelado = true; if (timer) clearTimeout(timer); };
  }, [machineId, eqId, rodada]);

  const iniciado = rodada > 0;
  const terminado = iniciado && (!!erro || !!teste?.concluido);
  const emAndamento = iniciado && !terminado;
  useEffect(() => {
    if (!emAndamento) return;
    const t = setInterval(() => setAgoraMs(Date.now()), 250);
    return () => clearInterval(t);
  }, [emAndamento]);

  const segundos = teste?.concluido ? teste.segundos : (agoraMs - inicioMs) / 1000;
  const iniciar = useCallback(() => setRodada(r => r + 1), []);
  return { teste, erro, iniciado, terminado, emAndamento, segundos, iniciar };
}
