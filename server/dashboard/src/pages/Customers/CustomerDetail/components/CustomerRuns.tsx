import { useState } from "react";
import { Download, Info, Layers, Send } from "lucide-react";
import { downloadCustomerRunZip, resendCustomerRunEmail } from "../../../../api/client";
import { CustomerRun } from "../../../../api/types";
import StatusBadge from "../../../../components/StatusBadge";
import { useToast } from "../../../../components/Toast";
import { fmtDate } from "../../../../utils/date";
import { extractBlobError } from "../../../../utils/download";
import { apiErrorMessage } from "../../../../utils/errors";
import { isRunOpen, runTriggerLabel, runZipFilename } from "../runUtils";
import RunDetailsModal from "./RunDetailsModal";

// Rodadas de backup do cliente: cada rodada agrupa os backups das máquinas e gera 1 e-mail.
// A lista vem do polling da tela (index.tsx); onChanged pede um recarregamento após uma ação.
export default function CustomerRuns({ customerId, customerName, runs, onChanged }: {
  customerId: string;
  customerName: string;
  runs: CustomerRun[] | null;
  onChanged: () => void;
}) {
  const { toast } = useToast();
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [resendingId, setResendingId] = useState<string | null>(null);
  const [detailsId, setDetailsId] = useState<string | null>(null);

  // Busca a versão mais recente da rodada aberta no modal (atualiza junto com o polling)
  const detailsRun = detailsId ? runs?.find(r => r.id === detailsId) ?? null : null;

  const handleDownload = async (run: CustomerRun) => {
    setDownloadingId(run.id);
    try {
      await downloadCustomerRunZip(customerId, run.id, runZipFilename(customerName, run));
    } catch (err) {
      toast(await extractBlobError(err), "error");
    } finally { setDownloadingId(null); }
  };

  const handleResend = async (run: CustomerRun) => {
    if (!confirm(`Reenviar o e-mail da rodada de ${fmtDate(run.started_at)} (${runTriggerLabel(run)}) para os e-mails do cliente "${customerName}"?`)) return;
    setResendingId(run.id);
    try {
      const r = await resendCustomerRunEmail(customerId, run.id);
      if (r.email_sent) toast("E-mail da rodada reenviado.", "success");
      else toast("O servidor não conseguiu enviar o e-mail. Verifique os e-mails do cliente e o SMTP.", "error");
      onChanged();
    } catch (e) {
      toast(apiErrorMessage(e, "Erro ao reenviar o e-mail da rodada."), "error");
    } finally { setResendingId(null); }
  };

  return (
    <div style={{ marginBottom: 24 }}>
      <div className="flex items-center justify-between mb-3">
        <div className="section-title" style={{ marginBottom: 0 }}><Layers size={15} /> Rodadas de backup</div>
        <span className="text-xs text-muted">1 e-mail por rodada com todas as máquinas</span>
      </div>
      {runs === null ? (
        <div className="loading-state"><div className="spinner" /></div>
      ) : runs.length === 0 ? (
        <div className="empty-state" style={{ padding: 32 }}>Nenhuma rodada de backup registrada ainda.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Data/Hora</th><th>Tipo</th><th>Status</th><th>Máquinas OK</th><th>E-mail</th><th>Ações</th></tr>
            </thead>
            <tbody>
              {runs.map(run => {
                const open = isRunOpen(run);
                return (
                  <tr key={run.id}>
                    <td className="text-sm text-secondary">{fmtDate(run.started_at)}</td>
                    <td className="text-sm">{runTriggerLabel(run)}</td>
                    <td>
                      <StatusBadge status={run.status} />
                      {open && (
                        <div className="text-xs text-muted" style={{ marginTop: 4 }}>
                          prazo até {fmtDate(run.deadline_at, { short: true })}
                        </div>
                      )}
                    </td>
                    <td>
                      <span style={{ fontWeight: 600, color: run.machines_ok === run.machines_expected ? "var(--ok)" : open ? "var(--text-secondary)" : "var(--warn)" }}>
                        {run.machines_ok}/{run.machines_expected}
                      </span>
                      {open && (
                        <div className="text-xs text-muted" style={{ marginTop: 4 }}>
                          {run.machines_reported} de {run.machines_expected} reportaram
                        </div>
                      )}
                    </td>
                    <td className="text-sm">
                      {open
                        ? <span className="text-muted">aguardando</span>
                        : run.email_sent
                          ? <span style={{ color: "var(--ok)" }}>Enviado</span>
                          : <span style={{ color: "var(--err)" }}>Não enviado</span>}
                    </td>
                    <td>
                      <div className="flex gap-2">
                        <button className="btn-icon" title="Detalhes da rodada" onClick={() => setDetailsId(run.id)}>
                          <Info size={14} />
                        </button>
                        <button className="btn-icon" title={run.has_zip ? "Baixar ZIP da rodada" : "Nenhum ZIP nesta rodada"}
                          disabled={!run.has_zip || downloadingId === run.id} onClick={() => handleDownload(run)}>
                          {downloadingId === run.id ? <span className="spinner spinner-sm" /> : <Download size={14} />}
                        </button>
                        <button className="btn-icon" title={open ? "Disponível quando a rodada fechar" : "Reenviar e-mail da rodada"}
                          disabled={open || resendingId === run.id} onClick={() => handleResend(run)}>
                          {resendingId === run.id ? <span className="spinner spinner-sm" /> : <Send size={14} />}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {detailsRun && <RunDetailsModal run={detailsRun} onClose={() => setDetailsId(null)} />}
    </div>
  );
}
