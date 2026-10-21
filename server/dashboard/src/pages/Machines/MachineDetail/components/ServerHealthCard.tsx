import { useMemo, useState } from "react";
import {
  Activity,
  ArrowDown,
  ArrowUp,
  ChevronRight,
  Cpu,
  Gauge,
  HardDrive,
  MemoryStick,
  Network,
} from "lucide-react";
import { fmtDate } from "../../../../utils/date";
import { cardTitleStyle, serverUtcMs } from "../utils";
import {
  fmtAgo,
  fmtGb,
  fmtMbps,
  fmtPct,
  LEVEL_COLOR,
  LEVEL_LABEL,
  levelOf,
  overallLevel,
  parseTelemetry,
  TelemetryDisk,
  TelemetryNet,
} from "../telemetry";
import { PctBar } from "./TelemetryBar";
import ServerHealthModal from "./ServerHealthModal";

interface Props {
  telemetry: Record<string, any> | null | undefined;
  lastSeen: string | null;
  isAgentOnline: boolean;
  nowMs: number;
  machineName: string;
}

interface MetricTileProps {
  icon: React.ReactNode;
  label: string;
  percent: number | null;
  caption: string;
}

export function MetricTile({ icon, label, percent, caption }: MetricTileProps) {
  const level = levelOf(percent);
  const color = level ? LEVEL_COLOR[level] : "var(--text-primary)";

  return (
    <div
      style={{
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-sm)",
        padding: "10px 12px",
        minWidth: 0,
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
        {icon}
        <span>{label}</span>
      </div>
      <div style={{ fontSize: 20, fontWeight: 700, color, lineHeight: 1.1 }}>
        {fmtPct(percent)}
      </div>
      <PctBar percent={percent} height={4} />
      <div
        style={{
          fontSize: 11,
          color: "var(--text-muted)",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
        title={caption}
      >
        {caption}
      </div>
    </div>
  );
}

export function SectionTitle({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 4,
        fontSize: 10,
        fontWeight: 600,
        letterSpacing: "0.5px",
        textTransform: "uppercase",
        color: "var(--text-muted)",
        marginBottom: 8,
      }}
    >
      {icon}
      <span>{children}</span>
    </div>
  );
}

export function DiskRow({ disk }: { disk: TelemetryDisk }) {
  const level = levelOf(disk.percent);
  const color = level ? LEVEL_COLOR[level] : "var(--text-primary)";

  return (
    <div
      style={{
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-sm)",
        padding: "10px 12px",
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div>
          <span style={{ fontWeight: 700, fontSize: 13, color: "var(--text-primary)" }}>
            {disk.device}
          </span>
          {disk.fstype && (
            <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 6 }}>
              {disk.fstype}
            </span>
          )}
        </div>
        <span style={{ fontWeight: 700, fontSize: 13, color }}>
          {fmtPct(disk.percent)}
        </span>
      </div>
      <PctBar percent={disk.percent} height={6} />
      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
        {`${fmtGb(disk.usedGb)} usados de ${fmtGb(disk.totalGb)} · ${fmtGb(disk.freeGb)} livres`}
      </div>
    </div>
  );
}

export function NicRow({ net }: { net: TelemetryNet }) {
  const isPhysical = !net.virtual;

  return (
    <div
      style={{
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderLeft: isPhysical ? "3px solid var(--cyan)" : "1px solid var(--border)",
        borderRadius: "var(--radius-sm)",
        padding: isPhysical ? "12px 14px" : "8px 12px",
        opacity: isPhysical ? 1 : 0.65,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <span
          style={{
            fontWeight: 700,
            fontSize: isPhysical ? 13 : 12,
            color: "var(--text-primary)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
          title={net.name}
        >
          {net.name}
        </span>
        <span
          style={{
            fontSize: 10,
            fontWeight: 600,
            textTransform: "uppercase",
            padding: "2px 6px",
            borderRadius: 4,
            flexShrink: 0,
            background: isPhysical ? "var(--cyan-glow)" : "var(--surface-2)",
            color: isPhysical ? "var(--cyan)" : "var(--text-muted)",
          }}
        >
          {isPhysical ? "Física" : "Virtual"}
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <ArrowUp size={isPhysical ? 14 : 11} color="var(--cyan)" style={{ flexShrink: 0 }} />
            <span
              style={{
                fontWeight: 700,
                fontSize: isPhysical ? 18 : 13,
                color: "var(--text-primary)",
                lineHeight: 1.2,
              }}
            >
              {fmtMbps(net.sentMbps)}
            </span>
          </div>
          <div
            style={{
              fontSize: 10,
              color: "var(--text-muted)",
              textTransform: "uppercase",
              letterSpacing: "0.5px",
              marginTop: 2,
            }}
          >
            Envio
          </div>
        </div>

        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <ArrowDown size={isPhysical ? 14 : 11} color="var(--ok)" style={{ flexShrink: 0 }} />
            <span
              style={{
                fontWeight: 700,
                fontSize: isPhysical ? 18 : 13,
                color: "var(--text-primary)",
                lineHeight: 1.2,
              }}
            >
              {fmtMbps(net.recvMbps)}
            </span>
          </div>
          <div
            style={{
              fontSize: 10,
              color: "var(--text-muted)",
              textTransform: "uppercase",
              letterSpacing: "0.5px",
              marginTop: 2,
            }}
          >
            Recebimento
          </div>
        </div>
      </div>
    </div>
  );
}

// Card "Saúde do Servidor": resumo da telemetria do último ping; os detalhes ficam no modal
export default function ServerHealthCard({
  telemetry,
  lastSeen,
  isAgentOnline,
  nowMs,
  machineName,
}: Props) {
  const t = useMemo(() => parseTelemetry(telemetry), [telemetry]);
  const [showDetails, setShowDetails] = useState(false);

  const level = t ? overallLevel(t) : null;

  const badge = useMemo(() => {
    if (!isAgentOnline) {
      return { cls: "muted", label: "Offline", dot: false };
    }
    if (level === null) {
      return { cls: "muted", label: "Sem dados", dot: false };
    }
    return { cls: level, label: LEVEL_LABEL[level], dot: true };
  }, [isAgentOnline, level]);

  const freshness = useMemo(() => {
    if (!lastSeen) return "";
    if (isAgentOnline) {
      return "Atualizado " + fmtAgo(nowMs - serverUtcMs(lastSeen));
    }
    return "Última leitura em " + fmtDate(lastSeen, { short: true }) + " — agente offline";
  }, [isAgentOnline, lastSeen, nowMs]);

  return (
    <div className="card" style={{ padding: "20px 24px" }}>
      <div style={{ ...cardTitleStyle, marginBottom: 6 }}>
        <Activity size={13} />
        <span>Saúde do Servidor</span>
        {t && (
          <span className={"badge " + badge.cls} style={{ marginLeft: "auto" }}>
            {badge.dot && <span className={"dot " + badge.cls} />}
            {badge.label}
          </span>
        )}
      </div>

      {!t ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)", fontStyle: "italic" }}>
          Sem dados de telemetria
        </div>
      ) : (
        <>
          {freshness && (
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 14 }}>
              {freshness}
            </div>
          )}

          <div
            style={{
              opacity: isAgentOnline ? 1 : 0.6,
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            {/* CPU, RAM e GPU */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(84px, 1fr))",
                gap: 8,
              }}
            >
              <MetricTile
                icon={<Cpu size={11} />}
                label="CPU"
                percent={t.cpuPercent}
                caption="Processador"
              />

              <MetricTile
                icon={<MemoryStick size={11} />}
                label="RAM"
                percent={t.ramPercent}
                caption={`${fmtGb(t.ramUsedGb)} de ${fmtGb(t.ramTotalGb)}`}
              />

              {t.gpu && (
                <MetricTile
                  icon={<Gauge size={11} />}
                  label="GPU"
                  percent={t.gpu.percent}
                  caption={t.gpu.name}
                />
              )}
            </div>

            {/* Discos */}
            {t.disks.length > 0 && (
              <div>
                <SectionTitle icon={<HardDrive size={11} />}>
                  {`Discos (${t.disks.length})`}
                </SectionTitle>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {t.disks.map((d, i) => (
                    <DiskRow key={d.device + i} disk={d} />
                  ))}
                </div>
              </div>
            )}

            {/* Rede */}
            {t.networks.length > 0 && (
              <div>
                <SectionTitle icon={<Network size={11} />}>
                  {`Rede (${t.networks.length})`}
                </SectionTitle>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {t.networks.map((net, i) => (
                    <NicRow key={net.name + i} net={net} />
                  ))}
                </div>
              </div>
            )}

            <button
              className="btn btn-secondary"
              style={{ width: "100%", justifyContent: "center" }}
              onClick={() => setShowDetails(true)}
            >
              Ver detalhes <ChevronRight size={14} />
            </button>
          </div>

          {showDetails && (
            <ServerHealthModal
              t={t}
              machineName={machineName}
              badge={badge}
              freshness={freshness}
              onClose={() => setShowDetails(false)}
            />
          )}
        </>
      )}
    </div>
  );
}
