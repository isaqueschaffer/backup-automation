import StatusBadge from "../../../components/StatusBadge";
import { fmtDate } from "../../../utils/date";
import { DadosHistorico, WidgetInstancia } from "../types";

interface Props {
  dados: DadosHistorico;
  widget: WidgetInstancia;
}

function fmtDuracao(segundos: number | null): string {
  if (segundos === null || !Number.isFinite(segundos)) return "—";
  if (segundos < 60) return `${segundos}s`;
  const min = Math.floor(segundos / 60);
  const sec = segundos % 60;
  if (min < 60) return `${min}m ${sec}s`;
  const h = Math.floor(min / 60);
  return `${h}h ${min % 60}m`;
}

const ROTULO_PERIODO: Record<string, string> = {
  "24h": "Últimas 24 horas",
  "7d": "Últimos 7 dias",
  "30d": "Últimos 30 dias",
};

export default function HistoricoBackupsWidget({ dados, widget }: Props) {
  const visual = (widget.config?.visual as string) || "grafico";
  const periodoTexto = ROTULO_PERIODO[dados.periodo] || ROTULO_PERIODO["7d"];

  const dias = dados.dias || [];
  const maxVal = Math.max(
    1,
    ...dias.map((d) => (d.ok || 0) + (d.parcial || 0) + (d.erro || 0))
  );

  const viewBoxW = 500;
  const viewBoxH = 150;
  const margemTop = 18;
  const margemBottom = 26;
  const margemLeft = 24;
  const margemRight = 10;
  const chartW = viewBoxW - margemLeft - margemRight;
  const chartH = viewBoxH - margemTop - margemBottom;
  const baselineY = margemTop + chartH;

  const step = Math.max(1, Math.ceil(dias.length / 8));

  return (
    <div
      style={{
        height: "100%",
        overflow: "auto",
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          fontSize: 11,
          color: "var(--text-muted)",
          fontWeight: 500,
        }}
      >
        <span>{periodoTexto}</span>
        {visual === "grafico" && (
          <span>Máx. diário: {maxVal}</span>
        )}
      </div>

      {visual === "tabela" ? (
        <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
          {dados.recentes && dados.recentes.length > 0 ? (
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: 12,
                textAlign: "left",
              }}
            >
              <thead>
                <tr
                  style={{
                    borderBottom: "1px solid var(--border)",
                    color: "var(--text-secondary)",
                    fontSize: 11,
                  }}
                >
                  <th style={{ padding: "4px 6px" }}>Máquina</th>
                  <th style={{ padding: "4px 6px" }}>Início</th>
                  <th style={{ padding: "4px 6px" }}>Duração</th>
                  <th style={{ padding: "4px 6px", textAlign: "right" }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {dados.recentes.map((r, i) => (
                  <tr
                    key={`${r.maquina}-${r.inicio}-${i}`}
                    style={{
                      borderBottom: "1px solid var(--border)",
                    }}
                  >
                    <td
                      style={{
                        padding: "6px",
                        fontWeight: 500,
                        color: "var(--text-primary)",
                      }}
                    >
                      {r.maquina}
                    </td>
                    <td
                      style={{
                        padding: "6px",
                        color: "var(--text-secondary)",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {fmtDate(r.inicio, { short: true })}
                    </td>
                    <td
                      style={{
                        padding: "6px",
                        color: "var(--text-secondary)",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {fmtDuracao(r.duracao_s)}
                    </td>
                    <td style={{ padding: "6px", textAlign: "right" }}>
                      <StatusBadge status={r.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div
              style={{
                height: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--text-muted)",
                fontSize: 12,
              }}
            >
              Nenhum backup registrado no período.
            </div>
          )}
        </div>
      ) : (
        <div
          style={{
            flex: 1,
            minHeight: 0,
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
          }}
        >
          <div style={{ width: "100%", flex: 1, minHeight: 120 }}>
            <svg
              viewBox={`0 0 ${viewBoxW} ${viewBoxH}`}
              style={{ width: "100%", height: "100%", display: "block" }}
            >
              {/* Linhas de grade horizontais */}
              <line
                x1={margemLeft}
                y1={margemTop}
                x2={viewBoxW - margemRight}
                y2={margemTop}
                stroke="var(--border)"
                strokeDasharray="2 3"
              />
              <line
                x1={margemLeft}
                y1={margemTop + chartH / 2}
                x2={viewBoxW - margemRight}
                y2={margemTop + chartH / 2}
                stroke="var(--border)"
                strokeDasharray="2 3"
              />
              <line
                x1={margemLeft}
                y1={baselineY}
                x2={viewBoxW - margemRight}
                y2={baselineY}
                stroke="var(--border)"
              />

              {/* Barras empilhadas */}
              {dias.map((d, i) => {
                const slotW = chartW / dias.length;
                const barW = Math.max(3, Math.min(20, slotW * 0.65));
                const x = margemLeft + i * slotW + (slotW - barW) / 2;

                const hOk = ((d.ok || 0) / maxVal) * chartH;
                const hParcial = ((d.parcial || 0) / maxVal) * chartH;
                const hErro = ((d.erro || 0) / maxVal) * chartH;

                const yOk = baselineY - hOk;
                const yParcial = yOk - hParcial;
                const yErro = yParcial - hErro;

                const partesData = d.data.split("-");
                const rotuloDia =
                  partesData.length === 3 ? `${partesData[2]}/${partesData[1]}` : d.data;
                const exibirRotulo =
                  i % step === 0 || i === dias.length - 1;

                return (
                  <g key={d.data}>
                    {hOk > 0 && (
                      <rect
                        x={x}
                        y={yOk}
                        width={barW}
                        height={hOk}
                        fill="var(--ok)"
                        rx={hParcial === 0 && hErro === 0 ? 2 : 0}
                      >
                        <title>{`${d.data}: ${d.ok} OK`}</title>
                      </rect>
                    )}
                    {hParcial > 0 && (
                      <rect
                        x={x}
                        y={yParcial}
                        width={barW}
                        height={hParcial}
                        fill="var(--warn)"
                        rx={hErro === 0 ? 2 : 0}
                      >
                        <title>{`${d.data}: ${d.parcial} Parcial`}</title>
                      </rect>
                    )}
                    {hErro > 0 && (
                      <rect
                        x={x}
                        y={yErro}
                        width={barW}
                        height={hErro}
                        fill="var(--err)"
                        rx={2}
                      >
                        <title>{`${d.data}: ${d.erro} Erro`}</title>
                      </rect>
                    )}
                    {exibirRotulo && (
                      <text
                        x={margemLeft + i * slotW + slotW / 2}
                        y={baselineY + 16}
                        textAnchor="middle"
                        fontSize={10}
                        fill="var(--text-muted)"
                      >
                        {rotuloDia}
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>
          </div>

          {/* Legenda */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 16,
              fontSize: 11,
              color: "var(--text-secondary)",
              paddingTop: 4,
            }}
          >
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              <span className="dot ok" style={{ flexShrink: 0 }} /> OK
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              <span className="dot warn" style={{ flexShrink: 0 }} /> Parcial
            </span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
              <span className="dot err" style={{ flexShrink: 0 }} /> Erro
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
