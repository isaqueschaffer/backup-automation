import { LEVEL_COLOR, levelOf } from "../telemetry";

// Barra de uso colorida pelo nível (limites em telemetry.ts)
export function PctBar({ percent, height = 6 }: { percent: number | null; height?: number }) {
  const clamped = percent === null ? 0 : Math.max(0, Math.min(100, percent));
  const level = levelOf(percent);
  const color = level ? LEVEL_COLOR[level] : "var(--muted)";

  return (
    <div style={{ width: "100%", height, backgroundColor: "var(--surface-2)", borderRadius: height / 2, overflow: "hidden" }}>
      <div style={{ width: `${clamped}%`, height: "100%", backgroundColor: color, borderRadius: height / 2, transition: "width 0.3s ease" }} />
    </div>
  );
}

export default function TelemetryBar({ label, percent, info }: { label: string; percent: number | null; info: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
        <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{label}</span>
        <span style={{ color: "var(--text-muted)", fontSize: 11 }}>{info}</span>
      </div>
      <PctBar percent={percent} height={6} />
    </div>
  );
}
