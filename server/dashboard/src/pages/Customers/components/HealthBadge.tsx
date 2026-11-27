import { Customer } from "../../../api/types";

const HEALTH: Record<Customer["health"], { label: string; color: string; bg: string }> = {
  ALL_OK: { label: "Tudo OK", color: "var(--ok)", bg: "rgba(16,185,129,0.12)" },
  PARTIAL: { label: "Parcial", color: "var(--warn)", bg: "var(--warn-bg)" },
  ALL_ERROR: { label: "Crítico", color: "var(--err)", bg: "var(--err-bg)" },
  NO_DATA: { label: "Sem dados", color: "var(--text-muted)", bg: "rgba(255,255,255,0.05)" },
};

const pill: React.CSSProperties = {
  fontSize: 11, fontWeight: 700, padding: "2px 10px", borderRadius: 999, whiteSpace: "nowrap",
};

// Saúde do último backup das máquinas do cliente
export default function HealthBadge({ health }: { health: Customer["health"] }) {
  const h = HEALTH[health] || HEALTH.NO_DATA;
  return (
    <span style={{ ...pill, background: h.bg, color: h.color, border: `1px solid ${h.color}40` }}>
      {h.label}
    </span>
  );
}

export function QueueBadge() {
  return (
    <span style={{ ...pill, background: "rgba(245,158,11,0.12)", color: "var(--warn)", border: "1px solid rgba(245,158,11,0.3)" }}>
      ⏳ Fila em andamento
    </span>
  );
}
