import { fmtPct, LEVEL_COLOR, levelOf } from "../Machines/MachineDetail/telemetry";

interface Props {
  percent: number | null;
  label: string;
  caption?: string;
  size?: number;
}

// Medidor circular em anel (donut) com valor no centro e legendas embaixo
export default function RingGauge({ percent, label, caption, size = 58 }: Props) {
  const stroke = 6;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const clamped = percent === null ? 0 : Math.max(0, Math.min(100, percent));
  const level = levelOf(percent);
  const color = level ? LEVEL_COLOR[level] : "var(--muted)";
  const center = size / 2;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        textAlign: "center",
        gap: 3,
        width: size + 14,
        minWidth: 0,
      }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={center}
          cy={center}
          r={r}
          fill="none"
          stroke="var(--surface-2)"
          strokeWidth={stroke}
        />
        <circle
          cx={center}
          cy={center}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - clamped / 100)}
          transform={`rotate(-90 ${center} ${center})`}
          style={{ transition: "stroke-dashoffset 0.3s ease" }}
        />
        <text
          x={center}
          y={center}
          textAnchor="middle"
          dominantBaseline="central"
          fontSize={size * 0.22}
          fontWeight={700}
          fill="var(--text-primary)"
        >
          {fmtPct(percent)}
        </text>
      </svg>
      <div
        style={{
          fontSize: 10,
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: "0.4px",
          color: "var(--text-muted)",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
          maxWidth: "100%",
        }}
        title={label}
      >
        {label}
      </div>
      {caption && (
        <div
          style={{
            fontSize: 9,
            color: "var(--text-muted)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            maxWidth: "100%",
          }}
          title={caption}
        >
          {caption}
        </div>
      )}
    </div>
  );
}
