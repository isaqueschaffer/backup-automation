import { Activity, Cable, Edit2, FolderOpen, Image, PlugZap, RadioTower, RefreshCw, Siren, Trash2, Video } from "lucide-react";
import { NVR } from "../../../../api/types";
import { fmtDate } from "../../../../utils/date";
import { eqCor, eqIcone } from "./eqTipos";

// Selo do último "Testar conexão" gravado no equipamento
function SeloConexao({ eq }: { eq: NVR }) {
  const st = eq.conexao_status;
  const [cor, fundo, texto] = !st
    ? ["var(--text-muted)", "rgba(255,255,255,0.05)", "Conexão não testada"]
    : st.ok
      ? ["var(--ok)", "var(--ok-bg)", "Conectado"]
      : ["var(--err)", "var(--err-bg)", "Falha na conexão"];
  const dica = st
    ? `${st.mensagem || ""}
Testado em ${fmtDate(st.testado_em)}`.trim()
    : "Use \"Testar\" para o agente conferir o IP e o login deste equipamento.";
  return (
    <span title={dica} style={{
      fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: fundo, color: cor,
      display: "inline-flex", alignItems: "center", gap: 5, whiteSpace: "nowrap",
    }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: cor }} />
      {texto}{st ? ` · ${fmtDate(st.testado_em, { short: true })}` : ""}
    </span>
  );
}

export default function EqCard({ eq, somenteLeitura, onDelete, onViewRecording, onViewCameras, onViewTelemetry, onViewOlt, onTestConexao, onViewAlarmes, onViewAntenas, onEdit, onToggleActive }: {
  eq: NVR;
  somenteLeitura?: boolean;
  onDelete: () => void;
  onViewRecording: () => void;
  onViewCameras?: () => void;
  onViewTelemetry?: () => void;
  onViewOlt?: () => void;
  onTestConexao?: () => void;
  onViewAlarmes?: () => void;
  onViewAntenas?: () => void;
  onEdit: () => void;
  onToggleActive: () => void;
}) {
  const color = eqCor(eq.tipo);

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
        {eqIcone(eq.tipo)}
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 700, color: "var(--text-primary)", fontSize: 14 }}>{eq.name}</span>
          <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: `${color}18`, color, border: `1px solid ${color}30` }}>
            {eq.tipo}
          </span>
          {eq.active === false && (
            <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: `var(--warn-bg)`, color: "var(--warn)", border: `1px solid rgba(245,158,11,0.3)` }}>
              PAUSADO
            </span>
          )}
          <SeloConexao eq={eq} />
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
        {eq.tipo === "OLT" && onViewOlt && (
          eq.config_extra?.fabricante_olt === "VSOL" || eq.config_extra?.fabricante_olt === "HUAWEI"
          || String(eq.config_extra?.olts || "").trim()
        ) && (
          <button className="btn btn-secondary btn-sm" onClick={onViewOlt}
            style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Cable size={13} /> ONUs
          </button>
        )}
        {eq.tipo === "NVR" && onViewTelemetry && (
          <button className="btn btn-secondary btn-sm" onClick={onViewTelemetry}
            style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Activity size={13} /> Telemetria
          </button>
        )}
        {eq.tipo === "ANTENA" && onViewAntenas && (
          <button className="btn btn-secondary btn-sm" onClick={onViewAntenas}
            style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <RadioTower size={13} /> Antenas
          </button>
        )}
        {eq.tipo === "DEFENSE" && onViewAlarmes && (
          <button className="btn btn-secondary btn-sm" onClick={onViewAlarmes}
            style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Siren size={13} /> Alarmes
          </button>
        )}
        {!somenteLeitura && onTestConexao && (
          <button className="btn btn-secondary btn-sm" onClick={onTestConexao} title="O agente confere se alcança o equipamento e se o login funciona"
            style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <PlugZap size={13} /> Testar
          </button>
        )}
        {!somenteLeitura && (
          <>
            <button className="btn-icon" title={eq.active === false ? "Retomar Backup" : "Pausar Backup"} onClick={onToggleActive}>
              {eq.active === false ? <RefreshCw size={14} /> : <div style={{width:14, height:14, borderLeft:'3px solid currentColor', borderRight:'3px solid currentColor'}}/>}
            </button>
            <button className="btn-icon" title="Editar" onClick={onEdit}>
              <Edit2 size={14} />
            </button>
            <button className="btn-icon" style={{ color: "var(--err)" }} title="Remover" onClick={onDelete}>
              <Trash2 size={14} />
            </button>
          </>
        )}
      </div>
    </div>
  );
}
