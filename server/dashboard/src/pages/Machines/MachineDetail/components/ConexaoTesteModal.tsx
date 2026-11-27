import { Cable, CheckCircle2, Circle, Loader2, MinusCircle, RotateCw, XCircle } from "lucide-react";
import Modal from "../../../../components/Modal";
import { EtapaConexao } from "../../../../api/types";
import { fmtCronometro, percentualTeste, useTesteConexao } from "../useTesteConexao";

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
  const { teste, erro, terminado, segundos, iniciar } = useTesteConexao(machineId, eqId, {
    automatico: true, onConcluido: () => onConcluido?.(),
  });

  const sucesso = !erro && teste?.concluido && teste.ok;
  const falhou = !!erro || (teste?.concluido && !teste.ok);
  const corBarra = sucesso ? "var(--ok)" : falhou ? "var(--err)" : "var(--accent)";
  const etapaAtual = teste?.etapas.find(e => e.estado === "andamento");
  const pct = erro ? 100 : percentualTeste(teste);

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
            <button className="btn btn-secondary" onClick={iniciar} style={{ display: "flex", alignItems: "center", gap: 6 }}>
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
