import { Fragment } from "react";
import StatusBadge from "../../../components/StatusBadge";
import RingGauge from "../../Overview/RingGauge";
import Thermometer from "../../Overview/Thermometer";
import {
  fmtAgo,
  fmtGb,
  fmtIdade,
  fmtUptime,
} from "../../Machines/MachineDetail/telemetry";
import { DadosTelemetriaEquipamentos, WidgetInstancia } from "../types";

const TODAS_METRICAS = [
  "cpu",
  "ram",
  "uptime",
  "disco_uso",
  "disco_temperatura",
  "disco_saude",
  "disco_capacidade",
  "disco_idade",
];

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
        Nenhum gravador com telemetria. A telemetria vem do backup de NVR/DVR Hikvision, Intelbras e Motorola.
      </div>
    );
  }

  const ativas = new Set<string>(
    dados.metricas && dados.metricas.length > 0 ? dados.metricas : TODAS_METRICAS
  );
  const temMetricaDisco = Array.from(ativas).some((m) => m.startsWith("disco_"));

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

        const temLinhaCpu =
          eq.cpu_percent !== null || eq.ram_percent !== null || eq.uptime_seconds != null;
        const temDiscosComDado = temMetricaDisco && Boolean(eq.disks && eq.disks.length > 0);
        const temAlgoParaMostrar = temLinhaCpu || temDiscosComDado;

        const disks = eq.disks || [];
        const temStatus = disks.some((d) => Boolean(d.status));
        const temUso = disks.some((d) => d.percent != null);
        const temTemp = disks.some((d) => d.temperature_c != null);
        const temCapacidade = disks.some((d) => d.total_gb != null || d.free_gb != null);
        const temIdade = disks.some((d) => d.power_on_days != null);

        const colunasDiscos = ["max-content"];
        if (temStatus) colunasDiscos.push("max-content");
        if (temUso) colunasDiscos.push("max-content");
        if (temTemp) colunasDiscos.push("max-content");
        if (temCapacidade) colunasDiscos.push("max-content");
        if (temIdade) colunasDiscos.push("max-content");
        if (colunasDiscos.length === 1) colunasDiscos.push("max-content");

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

            {!temAlgoParaMostrar ? (
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                Sem dados para as métricas escolhidas
              </div>
            ) : (
              <>
                {/* Linha de anéis de CPU e RAM e tempo ligado */}
                {temLinhaCpu && (
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
                {temMetricaDisco && (
                  !eq.disks || eq.disks.length === 0 ? (
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      Sem dados de disco
                    </div>
                  ) : (
                    <div style={{ overflowX: "auto" }}>
                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: colunasDiscos.join(" "),
                          columnGap: 18,
                          rowGap: 8,
                          alignItems: "center",
                          justifyContent: "space-between",
                          minWidth: "min-content",
                          fontSize: 12,
                        }}
                      >
                        {eq.disks.map((d, idx) => {
                          const semDados =
                            d.total_gb == null &&
                            d.free_gb == null &&
                            d.percent == null &&
                            d.temperature_c == null &&
                            !d.status &&
                            d.power_on_days == null;

                          const partesCapacidade: string[] = [];
                          if (d.total_gb != null) partesCapacidade.push(fmtGb(d.total_gb));
                          if (d.free_gb != null) partesCapacidade.push(`${fmtGb(d.free_gb)} livres`);
                          const textoCapacidade = partesCapacidade.join(" · ");

                          return (
                            <Fragment key={d.device || idx}>
                              <span
                                style={{
                                  fontWeight: 600,
                                  color: "var(--text-primary)",
                                  whiteSpace: "nowrap",
                                  overflow: "hidden",
                                  textOverflow: "ellipsis",
                                  maxWidth: 100,
                                }}
                                title={d.device}
                              >
                                {d.device || "Disco"}
                              </span>

                              {semDados ? (
                                <span
                                  style={{
                                    gridColumn: "2 / -1",
                                    fontSize: 11,
                                    color: "var(--text-muted)",
                                  }}
                                >
                                  sem dados do disco
                                </span>
                              ) : (
                                <>
                                  {temStatus && (
                                    d.status ? <StatusBadge status={d.status} /> : <span />
                                  )}
                                  {temUso && (
                                    d.percent != null ? (
                                      <RingGauge percent={d.percent} size={40} />
                                    ) : (
                                      <span />
                                    )
                                  )}
                                  {temTemp && (
                                    d.temperature_c != null ? (
                                      <Thermometer
                                        celsius={d.temperature_c}
                                        height={52}
                                        inline
                                      />
                                    ) : (
                                      <span />
                                    )
                                  )}
                                  {temCapacidade && (
                                    textoCapacidade ? (
                                      <span
                                        style={{
                                          fontSize: 11,
                                          color: "var(--text-muted)",
                                          whiteSpace: "nowrap",
                                        }}
                                      >
                                        {textoCapacidade}
                                      </span>
                                    ) : (
                                      <span />
                                    )
                                  )}
                                  {temIdade && (
                                    d.power_on_days != null ? (
                                      <span
                                        style={{
                                          fontSize: 11,
                                          color: "var(--text-muted)",
                                          whiteSpace: "nowrap",
                                        }}
                                      >
                                        {fmtIdade(d.power_on_days)}
                                      </span>
                                    ) : (
                                      <span />
                                    )
                                  )}
                                </>
                              )}
                            </Fragment>
                          );
                        })}
                      </div>
                    </div>
                  )
                )}
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
