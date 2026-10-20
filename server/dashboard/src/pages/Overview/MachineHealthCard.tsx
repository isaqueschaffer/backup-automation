import { useMemo } from "react";
import {
  Activity,
  Cpu,
  EyeOff,
  Gauge,
  GripVertical,
  HardDrive,
  MemoryStick,
  Network,
  Server,
} from "lucide-react";
import { Machine } from "../../api/types";
import StatusBadge from "../../components/StatusBadge";
import { fmtDate, fmtSchedule } from "../../utils/date";
import {
  fmtAgo,
  fmtGb,
  LEVEL_LABEL,
  overallLevel,
  parseTelemetry,
} from "../Machines/MachineDetail/telemetry";
import { serverUtcMs } from "../Machines/MachineDetail/utils";
import {
  DiskRow,
  MetricTile,
  NicRow,
  SectionTitle,
} from "../Machines/MachineDetail/components/ServerHealthCard";
import { Span, SPANS } from "./layout";

interface Props {
  machine: Machine;
  nowMs: number;
  span: Span;
  editing: boolean;
  onSpanChange: (s: Span) => void;
  onHide: () => void;
}

// Card da máquina na Visão Geral com Saúde do Servidor em destaque
export default function MachineHealthCard({
  machine,
  nowMs,
  span,
  editing,
  onSpanChange,
  onHide,
}: Props) {
  const t = useMemo(() => parseTelemetry(machine.telemetry), [machine.telemetry]);
  const level = t ? overallLevel(t) : null;
  const isOnline = machine.active && machine.is_online;
  const customerInitial = (machine.customer_name || "S").charAt(0).toUpperCase();

  return (
    <div
      className="client-card"
      style={{
        cursor: editing ? "default" : "pointer",
        position: "relative",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        outline: editing ? "1px dashed var(--border-accent)" : undefined,
        outlineOffset: editing ? 2 : undefined,
      }}
    >
      {/* Faixa do modo edição: alça, largura e remover */}
      {editing && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 10,
            paddingBottom: 8,
            borderBottom: "1px solid var(--border)",
          }}
        >
          <span
            data-drag-handle
            title="Arraste para reordenar"
            style={{ display: "flex", cursor: "grab", color: "var(--text-muted)" }}
          >
            <GripVertical size={16} />
          </span>

          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            {SPANS.map(s => {
              const isActive = span === s.span;
              return (
                <button
                  key={s.span}
                  type="button"
                  title={`Largura: ${s.label}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onSpanChange(s.span);
                  }}
                  style={{
                    background: isActive ? "var(--accent)" : "var(--surface-2)",
                    color: isActive ? "#fff" : "var(--text-primary)",
                    border: "1px solid var(--border)",
                    padding: "2px 8px",
                    fontSize: 11,
                    borderRadius: 6,
                    cursor: "pointer",
                    fontWeight: isActive ? 600 : 400,
                  }}
                >
                  {s.label}
                </button>
              );
            })}
          </div>

          <button
            type="button"
            className="btn-icon"
            title="Remover da visão geral"
            onClick={(e) => {
              e.stopPropagation();
              onHide();
            }}
            style={{ marginLeft: "auto", width: 26, height: 26 }}
          >
            <EyeOff size={14} />
          </button>
        </div>
      )}

      <div className="client-card-header" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 12, alignItems: "center", minWidth: 0 }}>
          <div className="client-avatar">
            {customerInitial}
          </div>
          <div style={{ minWidth: 0 }}>
            <div
              className="client-name"
              style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              title={machine.customer_name || "Sem cliente"}
            >
              {machine.customer_name || "Sem cliente"}
            </div>
            <div
              style={{
                fontSize: 11,
                color: "var(--text-muted)",
                display: "flex",
                alignItems: "center",
                gap: 4,
                minWidth: 0,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={machine.name}
            >
              <Server size={11} style={{ flexShrink: 0 }} />
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {machine.name}
              </span>
            </div>
          </div>
        </div>
        <div style={{ flexShrink: 0, marginLeft: 8 }}>
          <StatusBadge status={machine.last_backup_status} />
        </div>
      </div>

      <div style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 6, marginBottom: 14 }}>
        {machine.active && machine.is_online ? (
          <>
            <span className="dot ok" />
            <span style={{ color: "var(--text-secondary)" }}>
              {machine.last_seen
                ? "Atualizado " + fmtAgo(nowMs - serverUtcMs(machine.last_seen))
                : "Aguardando a primeira comunicação"}
            </span>
          </>
        ) : machine.active ? (
          <>
            <span className="dot err" />
            <span style={{ color: "var(--text-muted)" }}>
              {"Offline · última comunicação " + fmtDate(machine.last_seen, { short: true, empty: "nunca" })}
            </span>
          </>
        ) : (
          <>
            <span className="dot" style={{ background: "var(--text-muted)" }} />
            <span style={{ color: "var(--text-muted)" }}>Máquina desativada</span>
          </>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <SectionTitle icon={<Activity size={11} />}>Saúde do Servidor</SectionTitle>
        {level && (
          <span className={"badge " + level} style={{ marginBottom: 8, padding: "2px 8px", fontSize: 10 }}>
            <span className={"dot " + level} />
            {LEVEL_LABEL[level]}
          </span>
        )}
      </div>

      {!t ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)", fontStyle: "italic", marginBottom: 12 }}>
          Sem dados de telemetria
        </div>
      ) : (
        <div
          style={{
            opacity: isOnline ? 1 : 0.6,
            display: "flex",
            flexDirection: "column",
            gap: 10,
            marginBottom: 12,
          }}
        >
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

          {/* Rede: placas físicas; as virtuais só em contagem */}
          {t.networks.length > 0 && (() => {
            const physicalNics = t.networks.filter(n => !n.virtual);
            const virtualNics = t.networks.filter(n => n.virtual);
            const showPhysical = physicalNics.length > 0;
            const displayNics = showPhysical ? physicalNics : virtualNics;
            const title = showPhysical
              ? `Rede (${physicalNics.length} física${physicalNics.length > 1 ? "s" : ""})`
              : `Rede (${virtualNics.length} virtual${virtualNics.length > 1 ? "is" : ""})`;

            return (
              <div>
                <SectionTitle icon={<Network size={11} />}>{title}</SectionTitle>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {displayNics.map((net, i) => (
                    <NicRow key={net.name + i} net={net} />
                  ))}
                  {showPhysical && virtualNics.length > 0 && (
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                      {`+${virtualNics.length} placa${virtualNics.length > 1 ? "s" : ""} virtual${virtualNics.length > 1 ? "is" : ""}`}
                    </div>
                  )}
                </div>
              </div>
            );
          })()}
        </div>
      )}

      <div
        style={{
          marginTop: "auto",
          paddingTop: 12,
          borderTop: "1px solid var(--border)",
          fontSize: 11,
          color: "var(--text-muted)",
        }}
      >
        {`${machine.nvr_count} equipamento${machine.nvr_count === 1 ? "" : "s"} · backup às ${fmtSchedule(machine.backup_hour, machine.backup_minute)} · último ${fmtDate(machine.last_backup_at, { short: true, empty: "nunca" })}`}
      </div>
    </div>
  );
}
