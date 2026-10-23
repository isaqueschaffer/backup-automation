import { ArrowDown, ArrowUp, Clock, Network } from "lucide-react";
import { NVRTelemetry } from "../../../../api/types";
import Modal from "../../../../components/Modal";
import StatusBadge from "../../../../components/StatusBadge";
import RingGauge from "../../../Overview/RingGauge";
import {
  fmtGb,
  fmtIdade,
  fmtMbps,
  fmtUptime,
  nivelTemperaturaHd,
  percentualTemperaturaHd,
} from "../telemetry";

export default function NVRTelemetryModal({ nvrName, telemetry, onClose }: {
  nvrName: string;
  telemetry: NVRTelemetry | null | undefined;
  onClose: () => void;
}) {
  const disks = telemetry?.disks || [];
  const networks = telemetry?.networks || [];
  const ramCaption =
    telemetry?.ram_used_gb != null && telemetry?.ram_total_gb != null
      ? `${fmtGb(telemetry.ram_used_gb)} de ${fmtGb(telemetry.ram_total_gb)}`
      : "Memória";

  return (
    <Modal title={`Telemetria — ${nvrName}`} onClose={onClose}>
      {!telemetry ? (
        <div className="empty-state">Sem dados de telemetria disponíveis.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {(telemetry.cpu_percent != null || telemetry.ram_percent != null || telemetry.uptime_seconds != null) && (
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 16 }}>
              {(telemetry.cpu_percent != null || telemetry.ram_percent != null) && (
                <>
                  <RingGauge
                    percent={telemetry.cpu_percent ?? null}
                    label="CPU"
                    caption="Processador"
                    size={72}
                  />
                  <RingGauge
                    percent={telemetry.ram_percent ?? null}
                    label="RAM"
                    caption={ramCaption}
                    size={72}
                  />
                </>
              )}
              {telemetry.uptime_seconds != null && (
                <div
                  style={{
                    background: "var(--surface-2)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-sm)",
                    padding: "10px 12px",
                    flex: "1 1 160px",
                    minWidth: 140,
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                      fontSize: 10,
                      fontWeight: 600,
                      color: "var(--text-muted)",
                      letterSpacing: "0.5px",
                      textTransform: "uppercase",
                    }}
                  >
                    <Clock size={11} style={{ flexShrink: 0 }} />
                    <span>Tempo ligado</span>
                  </div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 6, minWidth: 0 }}>
                    <span style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)", lineHeight: 1.1 }}>
                      {fmtUptime(telemetry.uptime_seconds)}
                    </span>
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      color: "var(--text-muted)",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                    title="Desde o último reinício"
                  >
                    Desde o último reinício
                  </div>
                </div>
              )}
            </div>
          )}

          {networks.length > 0 && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", marginBottom: 8 }}>
                {`Rede (${networks.length})`}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {networks.map((n, i) => (
                  <div
                    key={i}
                    style={{
                      background: "var(--surface-2)",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--radius-sm)",
                      padding: "10px 12px",
                      display: "flex",
                      flexDirection: "column",
                      gap: 8,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Network size={14} color="var(--primary)" style={{ flexShrink: 0 }} />
                        <span style={{ fontWeight: 600, fontSize: 13, color: "var(--text-primary)" }}>{n.name}</span>
                        {n.status && <StatusBadge status={n.status} />}
                        {n.speed_mbps && (
                          <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 2 }}>
                            {n.speed_mbps >= 1000 ? `${(n.speed_mbps / 1000).toFixed(0)} Gbps` : `${n.speed_mbps} Mbps`}
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        {n.ip ? `IP: ${n.ip}` : ""} {n.mac ? `${n.ip ? " · " : ""}MAC: ${n.mac}` : ""}
                      </div>
                    </div>

                    {(n.recv_mbps != null || n.sent_mbps != null) && (
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, paddingTop: 6, borderTop: "1px solid var(--border)" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <ArrowDown size={14} color="var(--ok)" style={{ flexShrink: 0 }} />
                          <div>
                            <div style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                              Recebimento (Câmeras)
                            </div>
                            <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", lineHeight: 1.2 }}>
                              {fmtMbps(n.recv_mbps ?? 0)}
                            </div>
                          </div>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <ArrowUp size={14} color="var(--cyan)" style={{ flexShrink: 0 }} />
                          <div>
                            <div style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                              Envio (Visualização)
                            </div>
                            <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", lineHeight: 1.2 }}>
                              {fmtMbps(n.sent_mbps ?? 0)}
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {disks.length === 0 ? (
            <div className="empty-state">Sem dados de disco disponíveis.</div>
          ) : (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", marginBottom: 8 }}>
                {`Discos (${disks.length})`}
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))",
                  gap: 10,
                }}
              >
                {disks.map((d, i) => {
                  const nomeDisco = d.device || `Disco ${i + 1}`;
                  const temAneis = d.percent != null || d.temperature_c != null;

                  return (
                    <div
                      key={i}
                      style={{
                        background: "var(--surface-2)",
                        border: "1px solid var(--border)",
                        borderRadius: "var(--radius-sm)",
                        padding: "10px 12px",
                        display: "flex",
                        flexDirection: "column",
                        gap: 8,
                        minWidth: 0,
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        <span
                          style={{
                            fontWeight: 600,
                            color: "var(--text-primary)",
                            whiteSpace: "nowrap",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                          }}
                          title={nomeDisco}
                        >
                          {nomeDisco}
                        </span>
                        <div style={{ flexShrink: 0 }}>
                          <StatusBadge status={d.status} />
                        </div>
                      </div>

                      {temAneis && (
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-around",
                            flexWrap: "wrap",
                            gap: 8,
                          }}
                        >
                          {d.percent != null && (
                            <RingGauge percent={d.percent} label="Uso" size={64} />
                          )}
                          {d.temperature_c != null && (
                            <RingGauge
                              percent={percentualTemperaturaHd(d.temperature_c)}
                              valueLabel={`${d.temperature_c}°`}
                              nivel={nivelTemperaturaHd(d.temperature_c)}
                              label="Temperatura"
                              caption={`${d.temperature_c} °C`}
                              size={64}
                            />
                          )}
                        </div>
                      )}

                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          fontSize: 11,
                          color: "var(--text-muted)",
                          gap: 2,
                        }}
                      >
                        <div>
                          {`Capacidade: ${fmtGb(d.total_gb ?? null)}`}
                          {d.free_gb != null && ` · ${fmtGb(d.free_gb)} livres`}
                        </div>
                        <div>
                          {`Idade: ${fmtIdade(d.power_on_days ?? null)}`}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
