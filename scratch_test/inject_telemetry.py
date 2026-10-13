import re

file_path = "server/dashboard/src/pages/ClientDetail.tsx"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Insert TelemetryBar
if "function TelemetryBar" not in content:
    telemetry_bar_code = """
function TelemetryBar({ label, percent, info }: { label: string, percent: number, info: string }) {
  const isHigh = percent > 90;
  const isWarn = percent > 75;
  const color = isHigh ? "var(--err)" : (isWarn ? "var(--warn)" : "var(--ok)");
  
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
        <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{label}</span>
        <span style={{ color: "var(--text-muted)", fontSize: 11 }}>{info}</span>
      </div>
      <div style={{ width: "100%", height: 6, backgroundColor: "var(--surface-2)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${percent}%`, height: "100%", backgroundColor: color, borderRadius: 3, transition: "width 0.3s ease" }}></div>
      </div>
    </div>
  );
}
"""
    content = content.replace("function InfoPill", telemetry_bar_code + "\nfunction InfoPill")

# 2. Update Grid Layout
import re
grid_pattern = r'\{\/\* ── Layout de duas colunas ── \*\/\}\s*<div style=\{\{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 \}\}>'
grid_replace = '{/* ── Layout de três colunas ── */}\n      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16, marginBottom: 24 }}>'
content = re.sub(grid_pattern, grid_replace, content)

# 3. Insert Telemetry Card
card_pattern = r'(<InfoPill icon=\{<CalendarCheck size=\{11\} \/>\} label="Data do .*? Backup"\s*value=\{fmtDate\(client\.last_backup_at\)\} \/>\s*<\/div>\s*<\/div>\s*)(<\/div>)'

card_code = r"""\1

        {/* Coluna 3 — Saúde da Máquina (Telemetria) */}
        <div className="card" style={{ padding: "20px 24px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--text-muted)", marginBottom: 16, display: "flex", alignItems: "center", gap: 6 }}>
            <Network size={13} /> Saúde do Servidor
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {client.telemetry ? (
              <>
                <TelemetryBar label="CPU" percent={client.telemetry.cpu_percent || 0} info={`${client.telemetry.cpu_percent || 0}%`} />
                <TelemetryBar label="RAM" percent={client.telemetry.ram_percent || 0} info={`${client.telemetry.ram_used_gb || 0} GB / ${client.telemetry.ram_total_gb || 0} GB`} />
                <TelemetryBar label="Disco (C:)" percent={client.telemetry.disk_percent || 0} info={`${client.telemetry.disk_free_gb || 0} GB Livre`} />
                {client.telemetry.networks && client.telemetry.networks.map((net: any, i: number) => (
                  <TelemetryBar 
                    key={i}
                    label={`Rede: ${net.name}`} 
                    percent={Math.min(100, (((net.mbps_sent || 0) + (net.mbps_recv || 0)) / 1000) * 100)} 
                    info={`↑ ${net.mbps_sent} Mbps  ↓ ${net.mbps_recv} Mbps`} 
                  />
                ))}
                {client.telemetry.gpu_name && (
                  <TelemetryBar label="GPU" percent={client.telemetry.gpu_percent || 0} info={`${client.telemetry.gpu_name} (${client.telemetry.gpu_percent || 0}%)`} />
                )}
              </>
            ) : (
              <div style={{ fontSize: 13, color: "var(--text-muted)", fontStyle: "italic" }}>Sem dados de telemetria</div>
            )}
          </div>
        </div>
      \2"""

content = re.sub(card_pattern, card_code, content)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Done")
