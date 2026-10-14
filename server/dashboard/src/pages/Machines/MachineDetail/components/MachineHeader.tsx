import { ArrowLeft, Clock, CloudLightning, Edit2, RefreshCw, RotateCcw } from "lucide-react";
import { Machine } from "../../../../api/types";
import StatusBadge from "../../../../components/StatusBadge";
import { fmtDate } from "../../../../utils/date";

// Cabeçalho da máquina: nome, último backup, ações e aviso de comando pendente
export default function MachineHeader({ machine, isAgentOnline, nextPingStr, onBack, onEdit, onRotateKey, onTriggerBackup, onRestartAgent }: {
  machine: Machine;
  isAgentOnline: boolean;
  nextPingStr: string;
  onBack: () => void;
  onEdit: () => void;
  onRotateKey: () => void;
  onTriggerBackup: () => void;
  onRestartAgent: () => void;
}) {
  const isPendingAction = machine.backup_requested || machine.restart_requested;
  return (
    <>
      <div className="page-header">
        <div className="flex items-center gap-3">
          <button className="btn-icon" onClick={onBack} title="Voltar para Máquinas">
            <ArrowLeft size={16} />
          </button>
          <div>
            <h1 className="page-title">{machine.name}</h1>
            <p className="page-subtitle flex items-center gap-2">
              <StatusBadge status={machine.last_backup_status} />
              {machine.last_backup_at && `Último backup: ${fmtDate(machine.last_backup_at)}`}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="btn btn-secondary" onClick={onEdit}>
            <Edit2 size={15} /> Editar Máquina
          </button>
          <button className="btn btn-secondary" onClick={onRotateKey}>
            <RefreshCw size={15} /> Rodar API Key
          </button>
          <button className="btn btn-secondary" onClick={onTriggerBackup}
            title={!isAgentOnline ? "Agente offline — o backup começará no próximo ping" : "Solicitar backup manual agora"}>
            <CloudLightning size={15} /> Gerar Backup
          </button>
          <button className="btn btn-secondary" onClick={onRestartAgent}
            title={!isAgentOnline ? "Agente offline — o reinício será executado no próximo ping" : "Reiniciar o agente Windows"}>
            <RotateCcw size={15} /> Reiniciar agente
          </button>
        </div>
      </div>

      {isPendingAction && (
        <div style={{ background: "rgba(245, 158, 11, 0.1)", border: "1px solid rgba(245, 158, 11, 0.3)", borderRadius: 6, padding: "12px 16px", marginBottom: 24, display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ color: "#f59e0b", display: "flex" }}><Clock size={18} /></div>
          <div style={{ fontSize: 13, color: "var(--text-primary)" }}>
            <strong>Comando na fila!</strong> O {machine.backup_requested ? "backup manual" : "reinício"} começará no próximo contato do agente
            {isAgentOnline && <span style={{ fontWeight: 600, color: "#f59e0b", marginLeft: 6 }}>({nextPingStr})</span>}.
          </div>
        </div>
      )}
    </>
  );
}
