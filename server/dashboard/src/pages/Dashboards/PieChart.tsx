export interface FatiaPizza {
  rotulo: string;
  valor: number;
  cor: string;
}

interface Props {
  fatias: FatiaPizza[];
  tamanho: number;
  rotuloCentro?: string;
}

export default function PieChart({ fatias, tamanho, rotuloCentro }: Props) {
  const cx = tamanho / 2;
  const cy = tamanho / 2;
  const r = tamanho / 2;

  const fatiasValidas = fatias.filter((f) => f.valor > 0);
  const total = fatiasValidas.reduce((acc, f) => acc + f.valor, 0);

  // Sem dados ou soma zero: círculo cinza com aviso central
  if (total <= 0 || fatiasValidas.length === 0) {
    return (
      <svg
        width={tamanho}
        height={tamanho}
        viewBox={`0 0 ${tamanho} ${tamanho}`}
        style={{ display: "block", flexShrink: 0 }}
      >
        <circle
          cx={cx}
          cy={cy}
          r={Math.max(0, r - 1)}
          fill="var(--surface-2)"
          stroke="var(--border)"
          strokeWidth={1}
        />
        <text
          x={cx}
          y={cy}
          textAnchor="middle"
          dominantBaseline="central"
          fill="var(--text-muted)"
          fontSize={Math.max(10, Math.round(tamanho * 0.12))}
        >
          Sem dados
        </text>
      </svg>
    );
  }

  const rFuro = r * 0.55;
  const fatiaCom100 = fatiasValidas.length === 1 || fatiasValidas[0].valor === total;

  return (
    <svg
      width={tamanho}
      height={tamanho}
      viewBox={`0 0 ${tamanho} ${tamanho}`}
      style={{ display: "block", flexShrink: 0 }}
    >
      {fatiaCom100 ? (
        <circle cx={cx} cy={cy} r={r} fill={fatiasValidas[0].cor}>
          <title>{`${fatiasValidas[0].rotulo}: ${fatiasValidas[0].valor} (100%)`}</title>
        </circle>
      ) : (
        (() => {
          let anguloAtual = -Math.PI / 2;
          return fatiasValidas.map((fatia, idx) => {
            const anguloFatia = (fatia.valor / total) * 2 * Math.PI;
            const anguloFim = anguloAtual + anguloFatia;

            const x1 = cx + r * Math.cos(anguloAtual);
            const y1 = cy + r * Math.sin(anguloAtual);
            const x2 = cx + r * Math.cos(anguloFim);
            const y2 = cy + r * Math.sin(anguloFim);

            const largeArcFlag = anguloFatia > Math.PI ? 1 : 0;
            const d = `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArcFlag} 1 ${x2} ${y2} Z`;
            const pct = Math.round((fatia.valor / total) * 100);

            anguloAtual = anguloFim;

            return (
              <path key={idx} d={d} fill={fatia.cor}>
                <title>{`${fatia.rotulo}: ${fatia.valor} (${pct}%)`}</title>
              </path>
            );
          });
        })()
      )}

      {/* Furo central do gráfico de rosca */}
      <circle cx={cx} cy={cy} r={rFuro} fill="var(--surface)" />

      {rotuloCentro !== undefined && rotuloCentro !== "" && (
        <text
          x={cx}
          y={cy}
          textAnchor="middle"
          dominantBaseline="central"
          fill="var(--text-primary)"
          fontWeight={700}
          fontSize={Math.max(10, Math.round(tamanho * (rotuloCentro.length > 3 ? 0.16 : 0.22)))}
        >
          {rotuloCentro}
        </text>
      )}
    </svg>
  );
}
