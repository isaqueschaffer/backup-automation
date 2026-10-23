import { statusTone } from "../utils/statusTone";

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
      {visible.map((item, index) => {
        const tone = statusTone(item.status);
        return (
          <span
            key={`dot-${index}`}
            title={item.title}
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              flexShrink: 0,
              boxSizing: "border-box",
              backgroundColor: tone === "muted" ? "transparent" : `var(--${tone})`,
              border: tone === "muted" ? "1.5px solid var(--text-muted)" : undefined,
            }}
          />
        );
      })}
    </span>
  );
}
