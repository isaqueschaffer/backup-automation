import StatusBadge from "../../../components/StatusBadge";
import RingGauge from "../../Overview/RingGauge";
import {
  fmtAgo,
  fmtGb,
  fmtIdade,
  fmtUptime,
  nivelTemperaturaHd,
  percentualTemperaturaHd,
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

            {/* Linha de anéis de CPU e RAM e tempo ligado */}
            {(eq.cpu_percent !== null || eq.ram_percent !== null || eq.uptime_seconds != null) && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 16,
                  padding: "2px 0",
                  flexWrap: "wrap",
                }}
              >
                {eq.cpu_percent !== null && (
                  <RingGauge percent={eq.cpu_percent} label="CPU" size={52} />
                )}
                {eq.ram_percent !== null && (
                  <RingGauge percent={eq.ram_percent} label="RAM" size={52} />
                )}
                {eq.uptime_seconds != null && (
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: 2,
                    }}
                  >
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 600,
                        textTransform: "uppercase",
                        color: "var(--text-muted)",
                      }}
                    >
                      Tempo ligado
                    </span>
                    <span
                      style={{
                        fontSize: 15,
                        fontWeight: 700,
                        color: "var(--text-primary)",
                      }}
                    >
                      {fmtUptime(eq.uptime_seconds)}
                    </span>
                  </div>
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
                  const semDados =
                    d.total_gb == null &&
                    d.percent == null &&
                    d.temperature_c == null;

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
                          flexWrap: "wrap",
                          justifyContent: "flex-end",
                          minWidth: 0,
                        }}
                      >
                        {semDados ? (
                          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                            sem dados do disco
                          </span>
                        ) : (
                          <>
                            {d.percent != null && (
                              <RingGauge percent={d.percent} size={40} />
                            )}
                            {d.temperature_c != null && (
                              <RingGauge
                                percent={percentualTemperaturaHd(d.temperature_c)}
                                valueLabel={`${d.temperature_c}°`}
                                nivel={nivelTemperaturaHd(d.temperature_c)}
                                size={40}
                              />
                            )}
                            <span
                              style={{
                                fontSize: 11,
                                color: "var(--text-muted)",
                                whiteSpace: "nowrap",
                              }}
                            >
                              {fmtGb(d.total_gb ?? null)}
                              {d.free_gb != null && ` · ${fmtGb(d.free_gb)} livres`}
                              {d.power_on_days != null && ` · ${fmtIdade(d.power_on_days)}`}
                            </span>
                          </>
                        )}
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
