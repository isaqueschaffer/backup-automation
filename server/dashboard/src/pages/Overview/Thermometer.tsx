import {
  LEVEL_COLOR,
  nivelTemperaturaHd,
  TEMP_HD_ATENCAO,
  TEMP_HD_CRITICA,
  TEMP_HD_ESCALA_MAX,
} from "../Machines/MachineDetail/telemetry";

interface Props {
  celsius: number | null;
  label?: string;
  caption?: string;
  height?: number;
}

// Termômetro vertical com escala em °C; marcas coloridas nos limites de atenção e crítico
export default function Thermometer({ celsius, label = "", caption, height = 80 }: Props) {
  const width = 46;
  const tubeW = 8;
  const bulbR = 8;
  const tubeX = 4 + bulbR - tubeW / 2;
  const cx = tubeX + tubeW / 2;
  const cy = height - bulbR - 1;
  const yTop = 5;
  const y0 = cy - 3;
  const yOf = (t: number) => y0 - (t / TEMP_HD_ESCALA_MAX) * (y0 - yTop);

  const nivel = nivelTemperaturaHd(celsius);
  const color = nivel ? LEVEL_COLOR[nivel] : "var(--muted)";
  const clamped = celsius === null ? 0 : Math.max(0, Math.min(TEMP_HD_ESCALA_MAX, celsius));
  const yFill = yOf(clamped);

  const passo = height >= 90 ? 10 : 20;
  const marcas: number[] = [];
  for (let t = 0; t <= TEMP_HD_ESCALA_MAX; t += passo) marcas.push(t);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        textAlign: "center",
        gap: 3,
        minWidth: 0,
      }}
    >
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <rect
          x={tubeX}
          y={yTop - 2}
          width={tubeW}
          height={cy - yTop}
          rx={tubeW / 2}
          fill="var(--surface-2)"
          stroke="var(--border)"
          strokeWidth={1}
        />
        <rect
          x={tubeX + 1.5}
          y={yFill}
          width={tubeW - 3}
          height={cy - yFill}
          rx={(tubeW - 3) / 2}
          fill={color}
          style={{ transition: "y 0.3s ease, height 0.3s ease" }}
        />
        <circle
          cx={cx}
          cy={cy}
          r={bulbR}
          fill={color}
          stroke="var(--border)"
          strokeWidth={1}
        />

        {marcas.map((t) => (
          <g key={t}>
            <line
              x1={tubeX + tubeW + 3}
              x2={tubeX + tubeW + 7}
              y1={yOf(t)}
              y2={yOf(t)}
              stroke="var(--text-muted)"
              strokeWidth={1}
            />
            <text
              x={tubeX + tubeW + 10}
              y={yOf(t)}
              dominantBaseline="central"
              fontSize={8}
              fill="var(--text-muted)"
            >
              {t}
            </text>
          </g>
        ))}

        <line
          x1={tubeX - 3}
          x2={tubeX + tubeW + 3}
          y1={yOf(TEMP_HD_ATENCAO)}
          y2={yOf(TEMP_HD_ATENCAO)}
          stroke="var(--warn)"
          strokeWidth={1.5}
        />
        <line
          x1={tubeX - 3}
          x2={tubeX + tubeW + 3}
          y1={yOf(TEMP_HD_CRITICA)}
          y2={yOf(TEMP_HD_CRITICA)}
          stroke="var(--err)"
          strokeWidth={1.5}
        />
      </svg>
      <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-primary)", whiteSpace: "nowrap" }}>
        {celsius === null ? "—" : `${celsius} °C`}
      </div>
      {Boolean(label) && (
        <div
          style={{
            fontSize: 10,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.4px",
            color: "var(--text-muted)",
            whiteSpace: "nowrap",
          }}
        >
          {label}
        </div>
      )}
      {caption && (
        <div style={{ fontSize: 9, color: "var(--text-muted)", whiteSpace: "nowrap" }}>
          {caption}
        </div>
      )}
    </div>
  );
}
