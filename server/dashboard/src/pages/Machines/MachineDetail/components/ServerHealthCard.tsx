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
  worstDisk,
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

function MetricTile({ icon, label, percent, caption }: MetricTileProps) {
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
            {/* CPU, RAM, disco mais cheio e GPU */}
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

              {t.disks.length > 0 && (() => {
                const d = worstDisk(t.disks)!;
                const label = t.disks.length === 1 ? "Disco" : `Discos (${t.disks.length})`;
                return (
                  <MetricTile
                    icon={<HardDrive size={11} />}
                    label={label}
                    percent={d.percent}
                    caption={`${d.device} · ${fmtGb(d.freeGb)} livres`}
                  />
                );
              })()}

              {t.gpu && (
                <MetricTile
                  icon={<Gauge size={11} />}
                  label="GPU"
                  percent={t.gpu.percent}
                  caption={t.gpu.name}
                />
              )}
            </div>

            {/* Placa de rede principal: física com mais tráfego */}
            {t.networks.length > 0 && (() => {
              const main = t.networks[0];
              return (
                <div style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                  <Network size={12} style={{ flexShrink: 0 }} />
                  <span
                    style={{
                      color: "var(--text-primary)",
                      fontWeight: 600,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                    title={main.name}
                  >
                    {main.name}
                  </span>
                  <span style={{ color: "var(--text-secondary)", whiteSpace: "nowrap", display: "inline-flex", alignItems: "center", gap: 3 }}>
                    <ArrowUp size={11} />
                    {fmtMbps(main.sentMbps)}
                  </span>
                  <span style={{ color: "var(--text-secondary)", whiteSpace: "nowrap", display: "inline-flex", alignItems: "center", gap: 3 }}>
                    <ArrowDown size={11} />
                    {fmtMbps(main.recvMbps)}
                  </span>
                  {t.networks.length > 1 && (
                    <span style={{ color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                      +{t.networks.length - 1}
                    </span>
                  )}
                </div>
              );
            })()}

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
