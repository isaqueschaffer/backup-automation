import { ArrowDown, ArrowUp, Cpu, MemoryStick, Network } from "lucide-react";
import { NVRTelemetry } from "../../../../api/types";
import Modal from "../../../../components/Modal";
import StatusBadge from "../../../../components/StatusBadge";
import { fmtGb, fmtMbps, fmtPct } from "../telemetry";
import { PctBar } from "./TelemetryBar";
import { MetricTile } from "./ServerHealthCard";

export default function NVRTelemetryModal({ nvrName, telemetry, onClose }: {
  nvrName: string;
  telemetry: NVRTelemetry | null | undefined;
  onClose: () => void;
}) {
  const disks = telemetry?.disks || [];
  const networks = telemetry?.networks || [];
  const ramSuffix = telemetry?.ram_total_gb ? `de ${fmtGb(telemetry.ram_total_gb)}` : undefined;
  const ramCaption = telemetry?.ram_used_gb != null
    ? `${fmtGb(telemetry.ram_used_gb)} em uso`
    : "Memória";

  return (
    <Modal title={`Telemetria — ${nvrName}`} onClose={onClose}>
      {!telemetry ? (
        <div className="empty-state">Sem dados de telemetria disponíveis.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(100px, 1fr))", gap: 8 }}>
            <MetricTile icon={<Cpu size={11} />} label="CPU" percent={telemetry.cpu_percent ?? null} caption="Processador" />
            <MetricTile
              icon={<MemoryStick size={11} />}
              label="RAM"
              percent={telemetry.ram_percent ?? null}
              caption={ramCaption}
              suffix={ramSuffix}
            />
          </div>

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
                        <Network size={14} color="var(--primary)" />
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
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Disco</th>
                      <th>Status</th>
                      <th>Uso</th>
                      <th>Capacidade</th>
                    </tr>
                  </thead>
                  <tbody>
                    {disks.map((d, i) => (
                      <tr key={i}>
                        <td>{d.device || `Disco ${i + 1}`}</td>
                        <td><StatusBadge status={d.status} /></td>
                        <td style={{ minWidth: 160 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <div style={{ flex: 1 }}><PctBar percent={d.percent ?? null} height={6} /></div>
                            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{fmtPct(d.percent ?? null)}</span>
                          </div>
                        </td>
                        <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                          {`${fmtGb(d.free_gb ?? null)} livres de ${fmtGb(d.total_gb ?? null)}`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
