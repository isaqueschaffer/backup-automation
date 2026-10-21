import { Cpu, MemoryStick } from "lucide-react";
import { NVRTelemetry } from "../../../../api/types";
import Modal from "../../../../components/Modal";
import StatusBadge from "../../../../components/StatusBadge";
import { fmtGb, fmtPct } from "../telemetry";
import { PctBar } from "./TelemetryBar";
import { MetricTile } from "./ServerHealthCard";

export default function NVRTelemetryModal({ nvrName, telemetry, onClose }: {
  nvrName: string;
  telemetry: NVRTelemetry | null | undefined;
  onClose: () => void;
}) {
  const disks = telemetry?.disks || [];

  return (
    <Modal title={`Telemetria — ${nvrName}`} onClose={onClose}>
      {!telemetry ? (
        <div className="empty-state">Sem dados de telemetria disponíveis.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(100px, 1fr))", gap: 8 }}>
            <MetricTile icon={<Cpu size={11} />} label="CPU" percent={telemetry.cpu_percent ?? null} caption="Processador" />
            <MetricTile icon={<MemoryStick size={11} />} label="RAM" percent={telemetry.ram_percent ?? null} caption="Memória" />
          </div>

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
