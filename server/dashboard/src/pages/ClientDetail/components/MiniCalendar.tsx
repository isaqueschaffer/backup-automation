export default function MiniCalendar({ mapStr, referenceDate }: { mapStr: string; referenceDate: string | null }) {
  if (!mapStr) return <span>—</span>;
  const refDate = referenceDate ? new Date(referenceDate) : new Date();
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "4px", width: "fit-content" }}>
      {mapStr.split("").map((char, i) => {
        const isOk = char === "█";
        const daysAgo = (mapStr.length - 1) - i;
        const d = new Date(refDate);
        d.setDate(d.getDate() - daysAgo);
        const dateStr = d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
        return (
          <div key={i} title={`${dateStr}: ${isOk ? "Gravou" : "Falhou"}`}
            style={{
              width: 26, height: 18, flexShrink: 0, borderRadius: 2,
              backgroundColor: isOk ? "var(--ok)" : "var(--err)",
              border: "1px solid rgba(255,255,255,0.15)", color: "white",
              display: "flex", cursor: "help", transition: "transform 0.1s",
              alignItems: "center", justifyContent: "center"
            }}
            onMouseEnter={e => e.currentTarget.style.transform = "scale(1.15)"}
            onMouseLeave={e => e.currentTarget.style.transform = "scale(1)"}
          >
            <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: "-0.3px" }}>{dateStr}</span>
          </div>
        );
      })}
    </div>
  );
}
