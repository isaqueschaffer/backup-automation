export default function TelemetryBar({ label, percent, info }: { label: string, percent: number, info: string }) {
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
