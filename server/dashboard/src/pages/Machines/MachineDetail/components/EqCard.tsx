import { Activity, Edit2, FolderOpen, Image, Network, Phone, RefreshCw, Trash2, Video, Wifi, WifiOff } from "lucide-react";
import { NVR } from "../../../../api/types";

export default function EqCard({ eq, onDelete, onViewRecording, onViewCameras, onViewTelemetry, onEdit, onToggleActive }: {
  eq: NVR;
  onDelete: () => void;
  onViewRecording: () => void;
  onViewCameras?: () => void;
  onViewTelemetry?: () => void;
  onEdit: () => void;
  onToggleActive: () => void;
}) {
  const getEqIcon = (tipo: string) => {
    const m: Record<string, React.ReactNode> = {
      NVR: <Video size={18} />, OLT: <Wifi size={18} />, ONU: <WifiOff size={18} />, PABX: <Phone size={18} />, MIKROTIK: <Network size={18} />, DIGIFORT: <Video size={18} />, DEFENSE: <Video size={18} />
    };
    return m[tipo] || <Video size={18} />;
  };
  const getEqColor = (tipo: string) => {
    const m: Record<string, string> = {
      NVR: "var(--primary)", OLT: "#10b981", ONU: "#f59e0b", PABX: "#8b5cf6", MIKROTIK: "#3b82f6", DIGIFORT: "#f43f5e", DEFENSE: "#ec4899"
    };
    return m[tipo] || "var(--text-muted)";
  };
  const color = getEqColor(eq.tipo);

  return (
    <div style={{
      background: "var(--surface-2, rgba(255,255,255,0.03))",
      border: "1px solid var(--border)", borderRadius: "var(--radius)",
      padding: "16px 20px", display: "flex", alignItems: "center", gap: 16,
      transition: "border-color 0.15s", opacity: eq.active === false ? 0.6 : 1
    }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = color)}
      onMouseLeave={e => (e.currentTarget.style.borderColor = "var(--border)")}
    >
      {/* Icon */}
      <div style={{
        width: 42, height: 42, borderRadius: "var(--radius-sm)", flexShrink: 0,
        background: `${color}18`, border: `1px solid ${color}40`,
        display: "flex", alignItems: "center", justifyContent: "center", color
      }}>
        {getEqIcon(eq.tipo)}
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <span style={{ fontWeight: 700, color: "var(--text-primary)", fontSize: 14 }}>{eq.name}</span>
          <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: `${color}18`, color, border: `1px solid ${color}30` }}>
            {eq.tipo}
          </span>
          {eq.active === false && (
            <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: `var(--warn-bg)`, color: "var(--warn)", border: `1px solid rgba(245,158,11,0.3)` }}>
              PAUSADO
            </span>
          )}
        </div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 12 }}>
          {eq.tipo === "OLT" || eq.tipo === "DIGIFORT" ? (
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <FolderOpen size={12} /> {eq.config_extra?.pasta_origem || "—"}
            </span>
          ) : (
            <>
              <span style={{ fontFamily: "monospace" }}>{eq.ip}</span>
              {eq.username && <span style={{ display: "flex", alignItems: "center", gap: 3 }}>👤 {eq.username}</span>}
            </>
          )}
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        {(eq.tipo === "NVR" || eq.tipo === "DIGIFORT" || eq.tipo === "DEFENSE") && onViewCameras && (
          <button className="btn btn-secondary btn-sm" onClick={onViewCameras}
            style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Image size={13} /> Galeria
          </button>
        )}
        {(eq.tipo === "NVR" || eq.tipo === "DIGIFORT" || eq.tipo === "DEFENSE") && (
          <button className="btn btn-secondary btn-sm" onClick={onViewRecording}
            style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Video size={13} /> Gravações
          </button>
        )}
        {eq.tipo === "NVR" && onViewTelemetry && (
          <button className="btn btn-secondary btn-sm" onClick={onViewTelemetry}
            style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Activity size={13} /> Telemetria
          </button>
        )}
        <button className="btn-icon" title={eq.active === false ? "Retomar Backup" : "Pausar Backup"} onClick={onToggleActive}>
          {eq.active === false ? <RefreshCw size={14} /> : <div style={{width:14, height:14, borderLeft:'3px solid currentColor', borderRight:'3px solid currentColor'}}/>}
        </button>
        <button className="btn-icon" title="Editar" onClick={onEdit}>
          <Edit2 size={14} />
        </button>
        <button className="btn-icon" style={{ color: "var(--err)" }} title="Remover" onClick={onDelete}>
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
}
