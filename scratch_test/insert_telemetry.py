import re

with open("server/dashboard/src/pages/ClientDetail.tsx", "r", encoding="utf-8") as f:
    content = f.read()

# Replace grid template columns
content = content.replace('gridTemplateColumns: "1fr 1fr"', 'gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))"')

# Add TelemetryBar component before InfoPill
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

if "function TelemetryBar" not in content:
    content = content.replace("function InfoPill", telemetry_bar_code + "function InfoPill")

# Add 3rd card
card3 = """
        {/* Coluna 3 - Saude da Maquina */}
        <div className="card" style={{ padding: "20px 24px" }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--text-muted)", marginBottom: 16, display: "flex", alignItems: "center", gap: 6 }}>
            <Network size={13} /> Saude do Servidor (Telemetria)
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {client.telemetry ? (
              <>
                <TelemetryBar label="CPU" percent={client.telemetry.cpu_percent || 0} info={`${client.telemetry.cpu_percent || 0}%`} />
                <TelemetryBar label="RAM" percent={client.telemetry.ram_percent || 0} info={`${client.telemetry.ram_used_gb || 0} GB / ${client.telemetry.ram_total_gb || 0} GB`} />
                <TelemetryBar label="Disco (C:)" percent={client.telemetry.disk_percent || 0} info={`${client.telemetry.disk_free_gb || 0} GB Livre`} />
                {client.telemetry.gpu_name && (
                  <TelemetryBar label="GPU" percent={client.telemetry.gpu_percent || 0} info={`${client.telemetry.gpu_name} (${client.telemetry.gpu_percent || 0}%)`} />
                )}
              </>
            ) : (
              <div style={{ fontSize: 13, color: "var(--text-muted)", fontStyle: "italic" }}>Sem dados de telemetria</div>
            )}
          </div>
        </div>
"""

# Finding the end of the Status card to insert card3
# Let's search for "Data do Último Backup" and then the two </div>s
match = re.search(r'(<InfoPill.*?label="Data do .*?Backup".*?/>\s*</div>\s*</div>)', content)
if match:
    content = content[:match.end()] + "\n" + card3 + content[match.end():]

with open("server/dashboard/src/pages/ClientDetail.tsx", "w", encoding="utf-8") as f:
    f.write(content)

print("Modified ClientDetail.tsx")
