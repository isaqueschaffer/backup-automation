import { Copy, Eye } from "lucide-react";
import Modal from "../../../components/Modal";

// Exibe uma única vez o ID e a API Key da máquina recém-criada
export default function NewMachineKeyModal({ machine, onCopy, onOpen, onClose }: {
  machine: { id: string; name: string; api_key: string };
  onCopy: (v: string) => void;
  onOpen: () => void;
  onClose: () => void;
}) {
  return (
    <Modal title="Máquina criada com sucesso!" onClose={onClose} wide>
      <div style={{ background: "var(--warn-bg)", border: "1px solid rgba(245,158,11,0.3)",
        borderRadius: "var(--radius-sm)", padding: "12px 16px", marginBottom: 20,
        color: "var(--warn)", fontSize: 13 }}>
        ⚠️ Copie a API Key agora. Ela não será exibida novamente.
      </div>
      <div className="form-group">
        <label className="form-label">ID da máquina (Client ID no agent.conf)</label>
        <div className="api-key-display">
          <span className="api-key-value">{machine.id}</span>
          <button className="btn-icon" onClick={() => onCopy(machine.id)}><Copy size={14} /></button>
        </div>
      </div>
      <div className="form-group">
        <label className="form-label">API Key (salve agora!)</label>
        <div className="api-key-display" style={{ borderColor: "rgba(245,158,11,0.4)" }}>
          <span className="api-key-value" style={{ color: "var(--warn)" }}>{machine.api_key}</span>
          <button className="btn-icon" onClick={() => onCopy(machine.api_key)}><Copy size={14} /></button>
        </div>
      </div>
      <p className="text-sm text-muted mt-2">
        Configure o arquivo <span className="font-mono">agent.conf</span> com esses valores na máquina Windows "{machine.name}".
      </p>
      <button className="btn btn-primary mt-4 w-full" style={{ justifyContent: "center" }} onClick={onOpen}>
        <Eye size={15} /> Ver detalhes da máquina
      </button>
    </Modal>
  );
}
