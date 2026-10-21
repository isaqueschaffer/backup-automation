import StatusBadge from "../../../components/StatusBadge";
import RingGauge from "../../Overview/RingGauge";
import {
  fmtAgo,
  fmtGb,
  fmtPct,
  LEVEL_COLOR,
  levelOf,
} from "../../Machines/MachineDetail/telemetry";
import { DadosTelemetriaEquipamentos, WidgetInstancia } from "../types";

export default function TelemetriaEquipamentosWidget({
  dados,
}: {
  dados: DadosTelemetriaEquipamentos;
  widget: WidgetInstancia;
}) {
  if (!dados.equipamentos || dados.equipamentos.length === 0) {
    return (
      <div
        style={{
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text-muted)",
          fontSize: 12,
          padding: 16,
          textAlign: "center",
        }}
      >
        Nenhum gravador com telemetria. A telemetria vem do backup de NVR/DVR Hikvision.
      </div>
    );
  }

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        gap: 10,
        fontSize: 12,
      }}
    >
      {dados.equipamentos.map((eq) => {
        const tempoAtualizado = eq.atualizado_em
          ? fmtAgo(Date.now() - new Date(eq.atualizado_em).getTime())
          : null;

        return (
          <div
            key={eq.id}
            style={{
              backgroundColor: "var(--surface-2)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 10,
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            {/* Cabeçalho */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 8,
                flexWrap: "wrap",
              }}
            >
              <div
                style={{
                  minWidth: 0,
                  display: "flex",
                  alignItems: "baseline",
                  gap: 6,
                  flexWrap: "wrap",
                }}
              >
                <span
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: "var(--text-primary)",
                  }}
                >
                  {eq.nome}
                </span>
                <span
                  style={{
                    fontSize: 11,
                    color: "var(--text-muted)",
                  }}
                >
                  · {eq.maquina}
                </span>
                {tempoAtualizado && (
                  <span
                    style={{
                      fontSize: 11,
                      color: "var(--text-muted)",
                    }}
                  >
                    · Atualizado {tempoAtualizado}
                  </span>
                )}
              </div>

              <span
                className={`badge ${eq.tem_problema ? "err" : "ok"}`}
                style={{ flexShrink: 0 }}
              >
                <span className={`dot ${eq.tem_problema ? "err" : "ok"}`} />
                {eq.tem_problema ? "Atenção" : "Saudável"}
              </span>
            </div>

            {/* Linha de anéis de CPU e RAM */}
            {(eq.cpu_percent !== null || eq.ram_percent !== null) && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 16,
                  padding: "2px 0",
                }}
              >
                {eq.cpu_percent !== null && (
                  <RingGauge percent={eq.cpu_percent} label="CPU" size={52} />
                )}
                {eq.ram_percent !== null && (
                  <RingGauge percent={eq.ram_percent} label="RAM" size={52} />
                )}
              </div>
            )}

            {/* Lista de discos */}
            {!eq.disks || eq.disks.length === 0 ? (
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                Sem dados de disco
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {eq.disks.map((d, idx) => {
                  const percentVal = d.percent ?? null;
                  const clampedPct =
                    percentVal === null
                      ? 0
                      : Math.max(0, Math.min(100, percentVal));
                  const level = levelOf(percentVal);
                  const corBarra = level ? LEVEL_COLOR[level] : "var(--text-muted)";

                  return (
                    <div
                      key={d.device || idx}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        flexWrap: "wrap",
                        gap: "6px 10px",
                        fontSize: 12,
                        minWidth: 0,
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          flexShrink: 0,
                          minWidth: 0,
                        }}
                      >
                        <span
                          style={{
                            fontWeight: 600,
                            color: "var(--text-primary)",
                            whiteSpace: "nowrap",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            maxWidth: 100,
                            flexShrink: 0,
                          }}
                          title={d.device}
                        >
                          {d.device || "Disco"}
                        </span>

                        <div style={{ flexShrink: 0 }}>
                          {d.status && <StatusBadge status={d.status} />}
                        </div>
                      </div>

                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          flex: "1 1 120px",
                          minWidth: 0,
                        }}
                      >
                        <div
                          style={{
                            flex: 1,
                            minWidth: 40,
                            height: 6,
                            borderRadius: 3,
                            backgroundColor: "var(--surface)",
                            overflow: "hidden",
                          }}
                        >
                          <div
                            style={{
                              width: `${clampedPct}%`,
                              height: "100%",
                              backgroundColor: corBarra,
                              borderRadius: 3,
                              transition: "width 0.3s ease",
                            }}
                          />
                        </div>

                        <span
                          style={{
                            fontSize: 11,
                            color: "var(--text-muted)",
                            whiteSpace: "nowrap",
                            flexShrink: 0,
                          }}
                        >
                          {percentVal === null && d.free_gb == null && d.total_gb == null
                            ? "sem dados do disco"
                            : `${fmtPct(percentVal)} · ${fmtGb(d.free_gb ?? null)} livres de ${fmtGb(d.total_gb ?? null)}`}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
