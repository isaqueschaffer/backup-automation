import { Copy } from "lucide-react";
import Modal from "../../../../components/Modal";

export default function RotatedKeyModal({ apiKey, onCopy, onClose }: {
  apiKey: string;
  onCopy: (v: string) => void;
  onClose: () => void;
}) {
  return (
    <Modal title="Nova API Key gerada" onClose={onClose}>
      <div style={{
        background: "var(--warn-bg)", border: "1px solid rgba(245,158,11,0.3)",
        borderRadius: "var(--radius-sm)", padding: "12px 16px", marginBottom: 20,
        color: "var(--warn)", fontSize: 13
      }}>
        ⚠️ Copie agora. Não será exibida novamente. Atualize o agent.conf na máquina.
      </div>
      <div className="api-key-display" style={{ borderColor: "rgba(245,158,11,0.4)" }}>
        <span className="api-key-value" style={{ color: "var(--warn)" }}>{apiKey}</span>
        <button className="btn-icon" onClick={() => onCopy(apiKey)}><Copy size={14} /></button>
      </div>
      <button className="btn btn-primary mt-4 w-full" style={{ justifyContent: "center" }}
        onClick={onClose}>Entendi</button>
    </Modal>
  );
}
