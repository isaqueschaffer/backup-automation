import { ArrowDown, ArrowUp } from "lucide-react";
import { DadosSaudeServidor, WidgetInstancia } from "../types";
import RingGauge from "../../Overview/RingGauge";
import {
  fmtAgo,
  fmtGb,
  fmtMbps,
  LEVEL_LABEL,
  overallLevel,
  parseTelemetry,
} from "../../Machines/MachineDetail/telemetry";

interface Props {
  dados: DadosSaudeServidor;
  widget: WidgetInstancia;
}

export default function SaudeServidorWidget({ dados }: Props) {
  if (!dados.maquinas || dados.maquinas.length === 0) {
    return (
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
        Nenhuma máquina encontrada.
      </div>
    );
  }

  return (
    <div
      style={{
        height: "100%",
        overflow: "auto",
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      {dados.maquinas.map((m) => {
        const t = parseTelemetry(m.telemetria);
        const lvl = t ? overallLevel(t) : null;
        const contatoMs = m.ultimo_contato
          ? new Date(
              m.ultimo_contato.endsWith("Z") ? m.ultimo_contato : m.ultimo_contato + "Z"
            ).getTime()
          : null;
        const tempoAgo =
          contatoMs && !Number.isNaN(contatoMs)
            ? `Atualizado ${fmtAgo(Date.now() - contatoMs)}`
            : "Sem comunicação";

        return (
          <div
            key={m.id}
            style={{
              backgroundColor: "var(--surface-2)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: "10px 12px",
              opacity: m.online ? 1 : 0.6,
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            {/* Cabeçalho da máquina */}
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
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  minWidth: 0,
                }}
              >
                <span
                  className={`dot ${m.online ? "ok" : "err"}`}
                  style={{ flexShrink: 0 }}
                />
                <span
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: "var(--text-primary)",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                  title={m.nome}
                >
                  {m.nome}
                </span>
                <span
                  style={{
                    fontSize: 11,
                    color: "var(--text-muted)",
                    whiteSpace: "nowrap",
                  }}
                >
                  · {tempoAgo}
                </span>
              </div>

              {lvl && (
                <span
                  className={`badge ${lvl}`}
                  style={{ padding: "1px 7px", fontSize: 9, flexShrink: 0 }}
                >
                  <span className={`dot ${lvl}`} style={{ flexShrink: 0 }} />
                  {LEVEL_LABEL[lvl]}
                </span>
              )}
            </div>

            {/* Medidores de telemetria */}
            {!t ? (
              <div
                style={{
                  fontSize: 12,
                  color: "var(--text-muted)",
                  fontStyle: "italic",
                }}
              >
                Sem dados de telemetria
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: "8px 10px",
                    alignItems: "flex-start",
                  }}
                >
                  <RingGauge percent={t.cpuPercent} label="CPU" size={52} />
                  <RingGauge
                    percent={t.ramPercent}
                    label="RAM"
                    caption={
                      t.ramUsedGb !== null && t.ramTotalGb !== null
                        ? `${fmtGb(t.ramUsedGb)}/${fmtGb(t.ramTotalGb)}`
                        : undefined
                    }
                    size={52}
                  />
                  {t.gpu && (
                    <RingGauge
                      percent={t.gpu.percent}
                      label="GPU"
                      caption={t.gpu.name}
                      size={52}
                    />
                  )}
                  {t.disks.map((d, i) => (
                    <RingGauge
                      key={`${d.device}-${i}`}
                      percent={d.percent}
                      label={d.device}
                      caption={
                        d.freeGb !== null ? `${fmtGb(d.freeGb)} livres` : undefined
                      }
                      size={52}
                    />
                  ))}
                </div>

                {/* Rede (até 2 interfaces físicas) */}
                {t.networks.length > 0 && (() => {
                  const physical = t.networks.filter((n) => !n.virtual);
                  const virtual = t.networks.filter((n) => n.virtual);
                  const targetList = physical.length > 0 ? physical : virtual;
                  const shown = targetList.slice(0, 2);

                  if (shown.length === 0) return null;

                  return (
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: 4,
                        paddingTop: 6,
                        borderTop: "1px solid var(--border)",
                      }}
                    >
                      {shown.map((net, i) => (
                        <div
                          key={`${net.name}-${i}`}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            fontSize: 11,
                            minWidth: 0,
                          }}
                        >
                          <span
                            style={{
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                              color: "var(--text-secondary)",
                              flex: 1,
                            }}
                            title={net.name}
                          >
                            {net.name}
                          </span>
                          <span
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 2,
                              fontWeight: 600,
                              whiteSpace: "nowrap",
                              color: "var(--text-primary)",
                            }}
                          >
                            <ArrowUp
                              size={11}
                              color="var(--cyan)"
                              style={{ flexShrink: 0 }}
                            />
                            {fmtMbps(net.sentMbps)}
                          </span>
                          <span
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 2,
                              fontWeight: 600,
                              whiteSpace: "nowrap",
                              color: "var(--text-primary)",
                            }}
                          >
                            <ArrowDown
                              size={11}
                              color="var(--accent)"
                              style={{ flexShrink: 0 }}
                            />
                            {fmtMbps(net.recvMbps)}
                          </span>
                        </div>
                      ))}
                    </div>
                  );
                })()}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
