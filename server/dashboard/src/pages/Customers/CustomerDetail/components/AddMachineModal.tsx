import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { fetchMachines } from "../../../../api/client";
import { Machine } from "../../../../api/types";
import Modal from "../../../../components/Modal";
import { fmtSchedule } from "../../../../utils/date";
import { useRotulos } from "../../../../contexts/AuthContext";

// Seletor de máquinas sem cliente para vincular a este cliente
export default function AddMachineModal({ customerName, scheduleLabel, attachingId, onAttach, onClose }: {
  customerName: string;
  scheduleLabel: string;
  attachingId: string | null;
  onAttach: (m: Machine) => void;
  onClose: () => void;
}) {
  const { singularMin } = useRotulos();
  const [machines, setMachines] = useState<Machine[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchMachines({ unassigned: true })
      .then(list => { if (!cancelled) setMachines(list); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, []);

  return (
    <Modal title={`Adicionar máquina a ${customerName}`} onClose={onClose}>
      <p className="text-sm text-muted" style={{ marginTop: 0, marginBottom: 16 }}>
        A máquina entra no fim da fila e passa a usar o horário do {singularMin} ({scheduleLabel}).
        Se o horário dela mudar, o agente é reiniciado automaticamente.
      </p>

      {failed ? (
        <div className="empty-state" style={{ padding: 24 }}>Não foi possível carregar as máquinas.</div>
      ) : machines === null ? (
        <div className="loading-state"><div className="spinner" /></div>
      ) : machines.length === 0 ? (
        <div className="empty-state" style={{ padding: 24 }}>
          <div>Não há máquinas sem {singularMin}.</div>
          <div className="text-sm mt-2">
            Cadastre uma nova máquina ou remova uma de outro {singularMin} em <Link to="/maquinas" onClick={onClose}>Máquinas</Link>.
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", maxHeight: 360, overflowY: "auto" }}>
          {machines.map((m, idx) => (
            <div key={m.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 14px", borderBottom: idx < machines.length - 1 ? "1px solid var(--border)" : "none" }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", flexShrink: 0, background: !m.active ? "var(--text-muted)" : m.is_online ? "var(--ok)" : "var(--err)" }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: "var(--text-primary)" }}>{m.name}</div>
                <div className="text-xs text-muted">
                  {m.nvr_count} equipamento(s) • horário atual {fmtSchedule(m.backup_hour, m.backup_minute)}
                </div>
              </div>
              <button className="btn btn-primary btn-sm" disabled={attachingId !== null} onClick={() => onAttach(m)}
                style={{ display: "flex", alignItems: "center", gap: 6 }}>
                {attachingId === m.id ? <span className="spinner spinner-sm" /> : <Plus size={13} />} Adicionar
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-3 mt-4" style={{ justifyContent: "flex-end" }}>
        <button className="btn btn-secondary" onClick={onClose}>Fechar</button>
      </div>
    </Modal>
  );
}
