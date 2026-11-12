import { useEffect, useRef, useState } from "react";
import { Cable, CheckCircle2, Circle, Loader2, MinusCircle, RotateCw, XCircle } from "lucide-react";
import Modal from "../../../../components/Modal";
import { iniciarTesteConexao, obterTesteConexao } from "../../../../api/client";
import { ConexaoTeste, EtapaConexao } from "../../../../api/types";

const INTERVALO_CONSULTA_MS = 1000;

function fmtCronometro(seg: number): string {
  const s = Math.max(0, Math.floor(seg));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

function erroDaApi(e: unknown): string {
  const detalhe = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detalhe === "string" ? detalhe : "Falha ao falar com o servidor.";
}

// Etapa feita conta 1; a em andamento conta meia, para a barra andar assim que ela começa
function percentual(t: ConexaoTeste | null): number {
  if (!t || t.etapas.length === 0) return 3;
  if (t.concluido) return 100;
  const feitas = t.etapas.reduce((soma, e) => soma + (e.estado === "andamento" ? 0.5 : e.estado === "pendente" ? 0 : 1), 0);
  return Math.max(3, Math.min(97, (feitas / t.etapas.length) * 100));
}

function IconeEtapa({ estado }: { estado: EtapaConexao["estado"] }) {
  if (estado === "ok") return <CheckCircle2 size={15} color="var(--ok)" />;
  if (estado === "erro") return <XCircle size={15} color="var(--err)" />;
  if (estado === "andamento") return <Loader2 size={15} color="var(--accent)" style={{ animation: "spin 0.9s linear infinite" }} />;
  if (estado === "pulado") return <MinusCircle size={15} color="var(--text-muted)" />;
  return <Circle size={15} color="var(--border)" />;
}

export default function ConexaoTesteModal({ machineId, eqId, eqNome, eqTipo, origem, onConcluido, onVerOnus, onClose }: {
  machineId: string;
  eqId: string;
  eqNome: string;
  eqTipo: string;
  /** "salvar": aberto logo depois do cadastro/edição */
  origem?: "salvar" | "card";
  onConcluido?: () => void;
  onVerOnus?: () => void;
  onClose: () => void;
}) {
  const [teste, setTeste] = useState<ConexaoTeste | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [rodada, setRodada] = useState(0);
  const [inicioMs, setInicioMs] = useState(() => Date.now());
  const [agoraMs, setAgoraMs] = useState(() => Date.now());
  const concluidoRef = useRef(onConcluido);
  concluidoRef.current = onConcluido;

  // Dispara o teste e consulta o andamento até terminar (nova rodada em "Testar de novo")
  useEffect(() => {
    let cancelado = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setTeste(null); setErro(null);
    setInicioMs(Date.now()); setAgoraMs(Date.now());

    const acompanhar = (atual: ConexaoTeste) => {
      if (cancelado) return;
      setTeste(atual);
      if (atual.concluido || !atual.task_id) {
        concluidoRef.current?.();
        return;
      }
      timer = setTimeout(async () => {
        try {
          acompanhar(await obterTesteConexao(machineId, eqId, atual.task_id!));
        } catch (e) {
          if (!cancelado) setErro(erroDaApi(e));
        }
      }, INTERVALO_CONSULTA_MS);
    };

    iniciarTesteConexao(machineId, eqId).then(acompanhar).catch(e => { if (!cancelado) setErro(erroDaApi(e)); });
    return () => { cancelado = true; if (timer) clearTimeout(timer); };
  }, [machineId, eqId, rodada]);

  const terminado = !!erro || !!teste?.concluido;
  useEffect(() => {
    if (terminado) return;
    const t = setInterval(() => setAgoraMs(Date.now()), 250);
    return () => clearInterval(t);
  }, [terminado]);

  const segundos = teste?.concluido ? teste.segundos : (agoraMs - inicioMs) / 1000;
  const sucesso = !erro && teste?.concluido && teste.ok;
  const falhou = !!erro || (teste?.concluido && !teste.ok);
  const corBarra = sucesso ? "var(--ok)" : falhou ? "var(--err)" : "var(--accent)";
  const etapaAtual = teste?.etapas.find(e => e.estado === "andamento");
  const pct = erro ? 100 : percentual(teste);

  const legenda = erro
    ? "Não foi possível concluir o teste"
    : teste?.concluido
      ? (teste.ok ? "Conexão confirmada" : "Falha na conexão")
      : etapaAtual?.rotulo || "Enviando o pedido ao agente...";

  return (
    <Modal title={`Testando conexão: ${eqNome}`} onClose={onClose} width={560}>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {origem === "salvar" && (
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
            Equipamento salvo. Agora o agente da máquina confere se alcança o equipamento e se o login funciona.
          </div>
        )}

        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8, gap: 12 }}>
            <span style={{ fontWeight: 700, fontSize: 14, color: sucesso ? "var(--ok)" : falhou ? "var(--err)" : "var(--text-primary)" }}>
              {legenda}
            </span>
            <span style={{ fontFamily: "monospace", fontSize: 13, color: "var(--text-muted)" }} title="Tempo decorrido">
              {fmtCronometro(segundos)}
            </span>
          </div>
          <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pct)}
            style={{ height: 10, borderRadius: 999, background: "var(--surface-2, rgba(255,255,255,0.06))", border: "1px solid var(--border)", overflow: "hidden" }}>
            <div className={terminado ? undefined : "barra-progresso-ativa"}
              style={{ width: `${pct}%`, height: "100%", background: corBarra, borderRadius: 999, transition: "width 0.5s ease, background 0.3s" }} />
          </div>
          {!terminado && eqTipo === "OLT" && (
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>
              Na OLT o teste já lê as ONUs e envia o status ao painel; com muitas ONUs pode levar alguns minutos.
            </div>
          )}
        </div>

        {teste && teste.etapas.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {teste.etapas.map(e => (
              <div key={e.id} style={{ display: "flex", gap: 10, alignItems: "flex-start", opacity: e.estado === "pendente" || e.estado === "pulado" ? 0.55 : 1 }}>
                <span style={{ marginTop: 1, flexShrink: 0 }}><IconeEtapa estado={e.estado} /></span>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13, color: "var(--text-primary)" }}>{e.rotulo}</div>
                  {e.detalhe && (
                    <div style={{ fontSize: 11, color: e.estado === "erro" ? "var(--err)" : "var(--text-muted)", wordBreak: "break-word" }}>{e.detalhe}</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {terminado && (erro || teste?.mensagem) && (
          <div style={{
            padding: "10px 12px", borderRadius: "var(--radius-sm)", fontSize: 13, lineHeight: 1.45,
            background: sucesso ? "var(--ok-bg)" : "var(--err-bg)",
            color: sucesso ? "var(--ok)" : "var(--err)",
          }}>
            {erro || teste?.mensagem}
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, flexWrap: "wrap" }}>
          {terminado && sucesso && eqTipo === "OLT" && onVerOnus && (
            <button className="btn btn-secondary" onClick={onVerOnus} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Cable size={14} /> Ver ONUs
            </button>
          )}
          {terminado && (
            <button className="btn btn-secondary" onClick={() => setRodada(r => r + 1)} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <RotateCw size={14} /> Testar de novo
            </button>
          )}
          <button className={terminado ? "btn btn-primary" : "btn btn-secondary"} onClick={onClose}>
            {terminado ? "Fechar" : "Fechar (o teste continua)"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
