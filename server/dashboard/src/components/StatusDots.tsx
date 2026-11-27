import { statusTone } from "../utils/statusTone";

function Dot({ tone, title }: { tone: string; title?: string }) {
  const isMuted = tone === "muted";
  return (
    <span
      title={title}
      aria-hidden={title ? undefined : "true"}
      style={{
        width: 10,
        height: 10,
        borderRadius: "50%",
        flexShrink: 0,
        boxSizing: "border-box",
        backgroundColor: isMuted ? "transparent" : `var(--${tone})`,
        border: isMuted ? "1.5px solid var(--text-muted)" : undefined,
      }}
    />
  );
}

export default function StatusDots({
  items,
  slots = 10,
}: {
  items: { status: string | null; title: string }[];
  slots?: number;
}) {
  const visible = slots > 0 ? items.slice(-slots) : [];
  const padCount = Math.max(0, slots - visible.length);

  return (
    <span
      aria-label="Resultado dos últimos backups"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
      }}
    >
      {Array.from({ length: padCount }, (_, i) => (
        <span
          key={`pad-${i}`}
          aria-hidden="true"
          style={{
            width: 10,
            height: 10,
            borderRadius: "50%",
            flexShrink: 0,
            boxSizing: "border-box",
            opacity: 0.25,
            border: "1px solid var(--border)",
            backgroundColor: "transparent",
          }}
        />
      ))}
      {visible.map((item, index) => (
        <Dot
          key={`dot-${index}`}
          tone={statusTone(item.status)}
          title={item.title}
        />
      ))}
    </span>
  );
}

const LEGEND_ITEMS: { tone: string; label: string }[] = [
  { tone: "ok", label: "OK" },
  { tone: "warn", label: "Parcial ou em andamento" },
  { tone: "err", label: "Erro ou não executou" },
  { tone: "muted", label: "Aguardando" },
];

export function StatusLegend() {
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: "6px 14px",
        fontSize: 11,
        color: "var(--text-muted)",
      }}
    >
      <span>Cada ponto é o resultado de uma rodada (do mais antigo ao mais recente):</span>
      {LEGEND_ITEMS.map((item) => (
        <span
          key={item.tone}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
          }}
        >
          <Dot tone={item.tone} />
          <span>{item.label}</span>
        </span>
      ))}
    </div>
  );
}
