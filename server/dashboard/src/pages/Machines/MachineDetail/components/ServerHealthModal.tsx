import {
  ArrowDown,
  ArrowUp,
  Cpu,
  Gauge,
  HardDrive,
  MemoryStick,
  Network,
} from "lucide-react";
import Modal from "../../../../components/Modal";
import { cardTitleStyle } from "../utils";
import TelemetryBar, { PctBar } from "./TelemetryBar";
import {
  CRIT_PCT,
  fmtGb,
  fmtMb,
  fmtMbps,
  fmtPct,
  LEVEL_COLOR,
  levelOf,
  Telemetry,
  WARN_PCT,
} from "../telemetry";

interface Props {
  t: Telemetry;
  machineName: string;
  badge: {
    cls: string;
    label: string;
    dot: boolean;
  };
  freshness: string;
  onClose: () => void;
}

const statBoxStyle: React.CSSProperties = {
  background: "var(--surface-2)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-sm)",
  padding: "10px 12px",
  minWidth: 0,
  display: "flex",
  flexDirection: "column",
  gap: 4,
};

const statBoxLabelStyle: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  color: "var(--text-muted)",
  letterSpacing: "0.5px",
  textTransform: "uppercase",
};

const statBoxValueStyle: React.CSSProperties = {
  fontSize: 16,
  fontWeight: 700,
  color: "var(--text-primary)",
};

// Detalhes da telemetria: cada disco, placa de rede e a GPU
export default function ServerHealthModal({
  t,
  machineName,
  badge,
  freshness,
  onClose,
}: Props) {
  const ramFreeGb =
    t.ramTotalGb !== null && t.ramUsedGb !== null ? t.ramTotalGb - t.ramUsedGb : null;

  return (
    <Modal wide title={"Saúde do Servidor — " + machineName} onClose={onClose}>
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span className={"badge " + badge.cls}>
            {badge.dot && <span className={"dot " + badge.cls} />}
            {badge.label}
          </span>
          {freshness && (
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              {freshness}
            </span>
          )}
        </div>

        <div>
          <div style={{ ...cardTitleStyle, marginBottom: 10 }}>
            <Cpu size={13} /> Processador
          </div>
          <TelemetryBar
            label="Uso"
            percent={t.cpuPercent}
            info={fmtPct(t.cpuPercent)}
          />
        </div>

        <div>
          <div style={{ ...cardTitleStyle, marginBottom: 10 }}>
            <MemoryStick size={13} /> Memória RAM
          </div>
          <TelemetryBar
            label="Uso"
            percent={t.ramPercent}
            info={`${fmtGb(t.ramUsedGb)} de ${fmtGb(t.ramTotalGb)}`}
          />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8, marginTop: 10 }}>
            <div style={statBoxStyle}>
              <div style={statBoxLabelStyle}>Usada</div>
              <div style={statBoxValueStyle}>{fmtGb(t.ramUsedGb)}</div>
            </div>
            <div style={statBoxStyle}>
              <div style={statBoxLabelStyle}>Livre</div>
              <div style={statBoxValueStyle}>{ramFreeGb !== null ? fmtGb(ramFreeGb) : "—"}</div>
            </div>
            <div style={statBoxStyle}>
              <div style={statBoxLabelStyle}>Total</div>
              <div style={statBoxValueStyle}>{fmtGb(t.ramTotalGb)}</div>
            </div>
          </div>
        </div>

        {t.disks.length > 0 && (
          <div>
            <div style={{ ...cardTitleStyle, marginBottom: 10 }}>
              <HardDrive size={13} /> Discos ({t.disks.length})
            </div>
            <div className="table-wrap">
              <div style={{ overflowX: "auto" }}>
                <table>
                  <thead>
                    <tr>
                      <th>Unidade</th>
                      <th>Sistema</th>
                      <th>Usado</th>
                      <th>Livre</th>
                      <th>Total</th>
                      <th>Uso</th>
                    </tr>
                  </thead>
                  <tbody>
                    {t.disks.map((d, idx) => {
                      const level = levelOf(d.percent);
                      const color = level ? LEVEL_COLOR[level] : "var(--text-primary)";
                      return (
                        <tr key={d.device + idx}>
                          <td style={{ fontWeight: 600 }}>{d.device}</td>
                          <td>{d.fstype ?? "—"}</td>
                          <td>{fmtGb(d.usedGb)}</td>
                          <td>{fmtGb(d.freeGb)}</td>
                          <td>{fmtGb(d.totalGb)}</td>
                          <td style={{ minWidth: 140 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <div style={{ flex: 1 }}>
                                <PctBar percent={d.percent} />
                              </div>
                              <span
                                style={{
                                  fontSize: 12,
                                  fontWeight: 600,
                                  color,
                                  minWidth: 38,
                                  textAlign: "right",
                                }}
                              >
                                {fmtPct(d.percent)}
                              </span>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {t.networks.length > 0 && (
          <div>
            <div style={{ ...cardTitleStyle, marginBottom: 10 }}>
              <Network size={13} /> Rede ({t.networks.length})
            </div>
            <div className="table-wrap">
              <div style={{ overflowX: "auto" }}>
                <table>
                  <thead>
                    <tr>
                      <th>Placa</th>
                      <th>Envio</th>
                      <th>Recebimento</th>
                      <th>Tipo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {t.networks.map((net, idx) => (
                      <tr key={net.name + idx}>
                        <td style={{ fontWeight: 600 }}>{net.name}</td>
                        <td>
                          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                            <ArrowUp size={11} /> {fmtMbps(net.sentMbps)}
                          </span>
                        </td>
                        <td>
                          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                            <ArrowDown size={11} /> {fmtMbps(net.recvMbps)}
                          </span>
                        </td>
                        <td>
                          <span style={net.virtual ? { color: "var(--text-muted)" } : {}}>
                            {net.virtual ? "Virtual" : "Física"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 6 }}>
              Taxa medida durante 1 segundo no último ping do agente.
            </div>
          </div>
        )}

        {t.gpu && (
          <div>
            <div style={{ ...cardTitleStyle, marginBottom: 10 }}>
              <Gauge size={13} /> GPU
            </div>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>
              {t.gpu.name}
            </div>
            <TelemetryBar
              label="Uso"
              percent={t.gpu.percent}
              info={fmtPct(t.gpu.percent)}
            />
            {(t.gpu.memUsedMb !== null || t.gpu.memTotalMb !== null) && (
              <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 8 }}>
                {"Memória: " + fmtMb(t.gpu.memUsedMb) + " de " + fmtMb(t.gpu.memTotalMb)}
              </div>
            )}
          </div>
        )}

        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
          {"Atenção acima de " + WARN_PCT + "% e crítico acima de " + CRIT_PCT + "% de uso."}
        </div>
      </div>
    </Modal>
  );
}
