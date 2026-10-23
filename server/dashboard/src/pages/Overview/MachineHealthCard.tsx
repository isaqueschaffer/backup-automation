import { useMemo } from "react";
import {
  Activity,
  ArrowDown,
  ArrowUp,
  EyeOff,
  GripVertical,
  Network,
  Server,
} from "lucide-react";
import { Machine } from "../../api/types";
import StatusBadge from "../../components/StatusBadge";
import { fmtDate, fmtSchedule } from "../../utils/date";
import {
  fmtAgo,
  fmtGb,
  fmtMbps,
  LEVEL_LABEL,
  overallLevel,
  parseTelemetry,
} from "../Machines/MachineDetail/telemetry";
import { serverUtcMs } from "../Machines/MachineDetail/utils";
import { Span, SPANS } from "./layout";
import RingGauge from "./RingGauge";

interface Props {
  machine: Machine;
  nowMs: number;
  span: Span;
  editing: boolean;
  onSpanChange: (s: Span) => void;
  onHide: () => void;
}

// Card compacto da máquina na Visão Geral com medidores em anel
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
        padding: "12px 14px",
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
            marginBottom: 8,
            paddingBottom: 6,
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

      {/* Cabeçalho */}
      <div className="client-card-header" style={{ marginBottom: 8 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", minWidth: 0 }}>
          <div
            className="client-avatar"
            style={{ width: 28, height: 28, fontSize: 12, borderRadius: 8 }}
          >
            {customerInitial}
          </div>
          <div style={{ minWidth: 0 }}>
            <div
              className="client-name"
              style={{ fontSize: 13, marginBottom: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              title={machine.customer_name || "Sem cliente"}
            >
              {machine.customer_name || "Sem cliente"}
            </div>
            <div
              style={{
                fontSize: 10,
                color: "var(--text-muted)",
                display: "flex",
                alignItems: "center",
                gap: 3,
                minWidth: 0,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={machine.name}
            >
              <Server size={10} style={{ flexShrink: 0 }} />
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {machine.name}
              </span>
            </div>
          </div>
        </div>
        <div style={{ transform: "scale(0.9)", transformOrigin: "right center", flexShrink: 0, marginLeft: 6 }}>
          <StatusBadge status={machine.last_backup_status} />
        </div>
      </div>

      {/* Linha de comunicação */}
      <div style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
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

      {/* Saúde do Servidor */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 4,
            fontSize: 10,
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.5px",
            color: "var(--text-muted)",
          }}
        >
          <Activity size={11} />
          <span>Saúde do Servidor</span>
        </div>
        {level && (
          <span className={"badge " + level} style={{ padding: "1px 7px", fontSize: 9 }}>
            <span className={"dot " + level} />
            {LEVEL_LABEL[level]}
          </span>
        )}
      </div>

      {!t ? (
        <div style={{ fontSize: 12, color: "var(--text-muted)", fontStyle: "italic", marginBottom: 8 }}>
          Sem dados de telemetria
        </div>
      ) : (
        <div style={{ opacity: isOnline ? 1 : 0.6 }}>
          {/* Anéis de métricas */}
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "10px 8px",
              justifyContent: "flex-start",
            }}
          >
            <RingGauge percent={t.cpuPercent} label="CPU" />
            <RingGauge
              percent={t.ramPercent}
              label="RAM"
              caption={`${fmtGb(t.ramUsedGb)}/${fmtGb(t.ramTotalGb)}`}
            />
            {t.gpu && (
              <RingGauge
                percent={t.gpu.percent}
                label="GPU"
                caption={t.gpu.name}
              />
            )}
            {t.disks.map((d, i) => (
              <RingGauge
                key={d.device + i}
                percent={d.percent}
                label={d.device}
                caption={`${fmtGb(d.freeGb)} livres`}
              />
            ))}
          </div>

          {/* Rede compacta */}
          {t.networks.length > 0 && (() => {
            const physicalNics = t.networks.filter(n => !n.virtual);
            const virtualNics = t.networks.filter(n => n.virtual);
            const primaryNics = physicalNics.length > 0 ? physicalNics : virtualNics;
            const shownNics = primaryNics.slice(0, 2);
            const hiddenCount = t.networks.length - shownNics.length;

            return (
              <div style={{ marginTop: 10 }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                    fontSize: 10,
                    fontWeight: 600,
                    textTransform: "uppercase",
                    letterSpacing: "0.5px",
                    color: "var(--text-muted)",
                    marginBottom: 6,
                  }}
                >
                  <Network size={11} />
                  <span>Rede</span>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                  {shownNics.map((net, i) => (
                    <div
                      key={net.name + i}
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
                          color: "var(--text-primary)",
                          fontWeight: 600,
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
                          fontWeight: 700,
                          whiteSpace: "nowrap",
                          color: "var(--text-primary)",
                        }}
                      >
                        <ArrowUp size={11} color="var(--cyan)" style={{ flexShrink: 0 }} />
                        {fmtMbps(net.sentMbps)}
                      </span>
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 2,
                          fontWeight: 700,
                          whiteSpace: "nowrap",
                          color: "var(--text-primary)",
                        }}
                      >
                        <ArrowDown size={11} color="var(--ok)" style={{ flexShrink: 0 }} />
                        {fmtMbps(net.recvMbps)}
                      </span>
                    </div>
                  ))}

                  {hiddenCount > 0 && (
                    <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>
                      {hiddenCount === 1 ? "+1 placa" : `+${hiddenCount} placas`}
                    </div>
                  )}
                </div>
              </div>
            );
          })()}
        </div>
      )}

      {/* Rodapé */}
      <div
        style={{
          marginTop: "auto",
          paddingTop: 8,
          borderTop: "1px solid var(--border)",
          fontSize: 10,
          color: "var(--text-muted)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        title={`${machine.nvr_count} equip. · backup ${fmtSchedule(machine.backup_hour, machine.backup_minute)} · último ${fmtDate(machine.last_backup_at, { short: true, empty: "nunca" })}`}
      >
        {`${machine.nvr_count} equip. · backup ${fmtSchedule(machine.backup_hour, machine.backup_minute)} · último ${fmtDate(machine.last_backup_at, { short: true, empty: "nunca" })}`}
      </div>
    </div>
  );
}
