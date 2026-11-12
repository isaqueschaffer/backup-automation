import { Copy } from "lucide-react";

export default function InfoPill({ icon, label, value, mono = false, copyValue, onCopy }: {
  icon: React.ReactNode; label: string; value: React.ReactNode;
  mono?: boolean; copyValue?: string; onCopy?: (v: string) => void;
}) {
  return (
    <div style={{
      display: "flex", flexDirection: "column", gap: 6,
      background: "var(--surface-2, rgba(255,255,255,0.03))",
      border: "1px solid var(--border)",
      borderRadius: "var(--radius-sm)", padding: "14px 16px"
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--text-muted)", fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.5px" }}>
        {icon}{label}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ color: "var(--text-primary)", fontFamily: mono ? "monospace" : undefined, fontSize: mono ? 12 : 14, fontWeight: 500, wordBreak: "break-all" }}>
          {value}
        </span>
        {copyValue && onCopy && (
          <button className="btn-icon" style={{ flexShrink: 0 }} onClick={() => onCopy(copyValue)}>
            <Copy size={12} />
          </button>
        )}
      </div>
    </div>
  );
}
