import { useState } from "react";
import { Link } from "react-router-dom";
import { Check, ChevronDown, ChevronRight, Download, Layers, Minus, Send } from "lucide-react";
import { downloadCustomerRunZip, resendCustomerRunEmail } from "../../../../api/client";
import { CustomerRun } from "../../../../api/types";
import StatusBadge from "../../../../components/StatusBadge";
import { useToast } from "../../../../components/Toast";
import { fmtDate } from "../../../../utils/date";
import { extractBlobError } from "../../../../utils/download";
import { apiErrorMessage } from "../../../../utils/errors";
import { isRunOpen, runTriggerLabel, runZipFilename } from "../runUtils";

// Rodadas de backup do cliente: cada rodada agrupa os backups das máquinas e gera 1 e-mail.
// A lista vem do polling da tela (index.tsx); onChanged pede um recarregamento após uma ação.
export default function CustomerRuns({
  customerId,
  customerName,
  runs,
  onChanged,
}: {
  customerId: string;
  customerName: string;
  runs: CustomerRun[] | null;
  onChanged: () => void;
}) {
  const { toast } = useToast();
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [resendingId, setResendingId] = useState<string | null>(null);
  const [verTodas, setVerTodas] = useState(false);
  const [expandidas, setExpandidas] = useState<Set<string>>(() => new Set());

  const toggleExpand = (id: string) => {
    setExpandidas((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleDownload = async (run: CustomerRun) => {
    setDownloadingId(run.id);
    try {
      await downloadCustomerRunZip(customerId, run.id, runZipFilename(customerName, run));
    } catch (err) {
      toast(await extractBlobError(err), "error");
    } finally {
      setDownloadingId(null);
    }
  };

  const handleResend = async (run: CustomerRun) => {
    if (
      !confirm(
        `Reenviar o e-mail da rodada de ${fmtDate(run.started_at)} (${runTriggerLabel(
          run
        )}) para os e-mails do cliente "${customerName}"?`
      )
    )
      return;
    setResendingId(run.id);
    try {
      const r = await resendCustomerRunEmail(customerId, run.id);
      if (r.email_sent) toast("E-mail da rodada reenviado.", "success");
      else
        toast(
          "O servidor não conseguiu enviar o e-mail. Verifique os e-mails do cliente e o SMTP.",
          "error"
        );
      onChanged();
    } catch (e) {
      toast(apiErrorMessage(e, "Erro ao reenviar o e-mail da rodada."), "error");
    } finally {
      setResendingId(null);
    }
  };

  const visiveis = runs ? (verTodas ? runs : runs.slice(0, 5)) : [];

  return (
    <div style={{ marginBottom: 24 }}>
      <div className="flex items-center justify-between mb-3">
        <div className="section-title" style={{ marginBottom: 0 }}>
          <Layers size={15} style={{ flexShrink: 0 }} /> Rodadas de backup
        </div>
        <span className="text-xs text-muted">1 e-mail por rodada com todas as máquinas</span>
      </div>

      {runs === null ? (
        <div className="loading-state">
          <div className="spinner" />
        </div>
      ) : runs.length === 0 ? (
        <div className="empty-state" style={{ padding: 32 }}>
          Nenhuma rodada de backup registrada ainda.
        </div>
      ) : (
        <>
          <div className="text-sm text-muted" style={{ marginBottom: 10 }}>
            Clique em uma rodada para ver o resultado de cada máquina.
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {visiveis.map((run) => {
              const open = isRunOpen(run);
              const isExpanded = open || expandidas.has(run.id);
              return (
                <div
                  key={run.id}
                  style={{
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-sm)",
                    backgroundColor: "var(--surface-2)",
                    overflow: "hidden",
                  }}
                >
                  {/* Linha de cabeçalho da rodada */}
                  <div
                    onClick={open ? undefined : () => toggleExpand(run.id)}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "auto 150px 1fr auto auto auto",
                      alignItems: "center",
                      gap: 12,
                      padding: "10px 14px",
                      cursor: open ? "default" : "pointer",
                      userSelect: "none",
                    }}
                  >
                    {/* Botão chevron */}
                    <div style={{ display: "flex", alignItems: "center" }}>
                      {open ? (
                        <ChevronDown size={14} style={{ opacity: 0.4, flexShrink: 0 }} />
                      ) : isExpanded ? (
                        <ChevronDown size={14} style={{ flexShrink: 0 }} />
                      ) : (
                        <ChevronRight size={14} style={{ flexShrink: 0 }} />
                      )}
                    </div>

                    {/* Data */}
                    <div className="text-sm text-secondary truncate">
                      {fmtDate(run.started_at)}
                    </div>

                    {/* Tipo */}
                    <div className="text-sm truncate">
                      {runTriggerLabel(run)}
                    </div>

                    {/* Status */}
                    <div>
                      <StatusBadge status={run.status} />
                    </div>

                    {/* Máquinas OK / Total */}
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span
                        style={{
                          fontWeight: 600,
                          color:
                            run.machines_ok === run.machines_expected
                              ? "var(--ok)"
                              : open
                              ? "var(--text-secondary)"
                              : "var(--warn)",
                        }}
                      >
                        {run.machines_ok}/{run.machines_expected}
                      </span>
                      {open && (
                        <span className="text-xs text-muted">
                          prazo até {fmtDate(run.deadline_at, { short: true })}
                        </span>
                      )}
                    </div>

                    {/* E-mail e Ações */}
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <span className="text-sm">
                        {open ? (
                          <span className="text-muted">aguardando</span>
                        ) : run.email_sent ? (
                          <span style={{ color: "var(--ok)" }}>Enviado</span>
                        ) : (
                          <span style={{ color: "var(--err)" }}>Não enviado</span>
                        )}
                      </span>
                      <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                        <button
                          className="btn-icon"
                          title={run.has_zip ? "Baixar ZIP da rodada" : "Nenhum ZIP nesta rodada"}
                          disabled={!run.has_zip || downloadingId === run.id}
                          onClick={() => handleDownload(run)}
                        >
                          {downloadingId === run.id ? (
                            <span className="spinner spinner-sm" />
                          ) : (
                            <Download size={14} style={{ flexShrink: 0 }} />
                          )}
                        </button>
                        <button
                          className="btn-icon"
                          title={open ? "Disponível quando a rodada fechar" : "Reenviar e-mail da rodada"}
                          disabled={open || resendingId === run.id}
                          onClick={() => handleResend(run)}
                        >
                          {resendingId === run.id ? (
                            <span className="spinner spinner-sm" />
                          ) : (
                            <Send size={14} style={{ flexShrink: 0 }} />
                          )}
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Painel expandido */}
                  {isExpanded && (
                    <div
                      style={{
                        borderTop: "1px solid var(--border)",
                        padding: "10px 14px",
                      }}
                    >
                      {run.machines.length === 0 ? (
                        <div className="text-sm text-muted">
                          Nenhuma máquina esperada nesta rodada.
                        </div>
                      ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                          {run.machines.map((m) => (
                            <div
                              key={m.machine_id}
                              style={{
                                display: "grid",
                                gridTemplateColumns: "1fr auto auto",
                                alignItems: "center",
                                gap: 12,
                                padding: "4px 0",
                              }}
                            >
                              <Link
                                to={`/maquinas/${m.machine_id}`}
                                style={{ color: "var(--text-primary)", fontWeight: 600 }}
                              >
                                {m.machine_name || "—"}
                              </Link>
                              <div>
                                {m.status !== null ? (
                                  <StatusBadge status={m.status} />
                                ) : (
                                  <span className="text-sm text-muted">aguardando relatório</span>
                                )}
                              </div>
                              <div
                                style={{
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                  width: 20,
                                }}
                              >
                                {m.zip ? (
                                  <span title="ZIP gerado" style={{ display: "inline-flex" }}>
                                    <Check
                                      size={14}
                                      style={{ color: "var(--ok)", flexShrink: 0 }}
                                    />
                                  </span>
                                ) : (
                                  <span title="Sem ZIP" style={{ display: "inline-flex" }}>
                                    <Minus
                                      size={14}
                                      style={{ color: "var(--text-muted)", flexShrink: 0 }}
                                    />
                                  </span>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                      {open && (
                        <div
                          className="text-xs text-muted"
                          style={{
                            marginTop: 8,
                            paddingTop: 8,
                            borderTop: "1px dashed var(--border)",
                          }}
                        >
                          {run.machines_reported} de {run.machines_expected} reportaram
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {runs.length > 5 && (
            <div style={{ marginTop: 12, textAlign: "center" }}>
              <button
                className="btn btn-secondary"
                style={{ fontSize: 12, padding: "4px 10px" }}
                onClick={() => setVerTodas((v) => !v)}
              >
                {verTodas ? "Ver menos" : `Ver todas (${runs.length})`}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
