import { Link } from "react-router-dom";
import { Check, Minus } from "lucide-react";
import { CustomerRun } from "../../../../api/types";
import Modal from "../../../../components/Modal";
import StatusBadge from "../../../../components/StatusBadge";
import { fmtDate } from "../../../../utils/date";
import { isRunOpen, runTriggerLabel } from "../runUtils";

// Detalhes de uma rodada: uma linha por máquina esperada (sem aninhamento na tabela principal)
export default function RunDetailsModal({ run, onClose }: { run: CustomerRun; onClose: () => void }) {
  const open = isRunOpen(run);
  return (
    <Modal title="Detalhes da rodada" onClose={onClose} width={720}>
      <div className="text-sm text-secondary" style={{ display: "flex", flexWrap: "wrap", gap: "6px 20px", marginBottom: 16 }}>
        <span><strong>Tipo:</strong> {runTriggerLabel(run)}</span>
        <span><strong>Início:</strong> {fmtDate(run.started_at)}</span>
        {open
          ? <span><strong>Prazo:</strong> {fmtDate(run.deadline_at)}</span>
          : <span><strong>Fechada:</strong> {fmtDate(run.closed_at)}</span>}
        <span><strong>E-mail:</strong> {open ? "aguardando fechamento" : run.email_sent ? "enviado" : "não enviado"}</span>
      </div>

      {run.machines.length === 0 ? (
        <div className="empty-state" style={{ padding: 24 }}>Nenhuma máquina esperada nesta rodada.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Máquina</th><th>Status</th><th>ZIP</th></tr>
            </thead>
            <tbody>
              {run.machines.map(m => (
                <tr key={m.machine_id}>
                  <td style={{ fontWeight: 600 }}>
                    <Link to={`/maquinas/${m.machine_id}`} style={{ color: "var(--text-primary)" }}>{m.machine_name || "—"}</Link>
                  </td>
                  <td>
                    {m.status
                      ? <StatusBadge status={m.status} />
                      : <span className="text-sm text-muted">aguardando relatório</span>}
                  </td>
                  <td>
                    {m.zip
                      ? <span title="ZIP recebido" style={{ color: "var(--ok)" }}><Check size={14} /></span>
                      : <span title="Sem ZIP" className="text-muted"><Minus size={14} /></span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {open && (
        <div className="text-xs text-muted" style={{ marginTop: 12 }}>
          A rodada fecha quando todas as máquinas reportarem (e o ZIP chegar) ou no prazo. Passado o prazo, ela
          espera as máquinas que ainda estão fazendo o backup (até 6 h no total). Máquinas sem relatório no
          fechamento aparecem como "Não executou" e o e-mail do cliente é enviado.
        </div>
      )}

      <div className="flex gap-3 mt-4" style={{ justifyContent: "flex-end" }}>
        <button className="btn btn-secondary" onClick={onClose}>Fechar</button>
      </div>
    </Modal>
  );
}
