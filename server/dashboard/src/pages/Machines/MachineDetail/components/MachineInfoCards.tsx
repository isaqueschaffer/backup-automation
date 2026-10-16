import { Archive, Building2, CalendarCheck, Clock, KeyRound, Mail, Network, Server, Wifi } from "lucide-react";
import { Machine } from "../../../../api/types";
import StatusBadge from "../../../../components/StatusBadge";
import { Link } from "react-router-dom";
import { fmtDate, fmtSchedule } from "../../../../utils/date";
import InfoPill from "./InfoPill";
import TelemetryBar from "./TelemetryBar";

const cardTitleStyle: React.CSSProperties = {
  fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.5px",
  color: "var(--text-muted)", marginBottom: 16, display: "flex", alignItems: "center", gap: 6,
};

// As três colunas do topo: Configuração, Status do Agente e Saúde do Servidor (telemetria)
export default function MachineInfoCards({ machine, customerEmails, isAgentOnline, nextPingStr, onCopy }: {
  machine: Machine;
  // E-mails do cliente quando a máquina os herda (null = não carregados: usa os da máquina)
  customerEmails: string[] | null;
  isAgentOnline: boolean;
  nextPingStr: string;
  onCopy: (v: string) => void;
}) {
  const emails = (machine.email_from_customer && customerEmails) || machine.email_to || [];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16, marginBottom: 24 }}>

      {/* Coluna 1 — Configuração */}
      <div className="card" style={{ padding: "20px 24px" }}>
        <div style={cardTitleStyle}>
          <Server size={13} /> Configuração da Máquina
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <InfoPill icon={<Building2 size={11} />} label="Cliente"
            value={machine.customer_id
              ? <><Link to={`/clientes/${machine.customer_id}`}>{machine.customer_name || "Cliente"}</Link>
                  <span className="text-muted" style={{ fontSize: 12 }}> (posição {(machine.queue_order ?? 0) + 1} na fila)</span></>
              : <span className="text-muted">Sem cliente</span>} />
          <InfoPill icon={<KeyRound size={11} />} label="ID da máquina (Client ID no agent.conf)" value={machine.id} mono copyValue={machine.id} onCopy={onCopy} />
          <InfoPill icon={<KeyRound size={11} />} label="API Key (prefixo)" value={`${machine.api_key_prefix}…`} mono />
          <InfoPill icon={<Clock size={11} />} label="Horário do Backup"
            value={`${fmtSchedule(machine.backup_hour, machine.backup_minute)} (diário)${machine.schedule_from_customer ? " — definido pelo cliente" : ""}`} />
          <InfoPill icon={<Mail size={11} />} label={machine.email_from_customer ? "E-mails do relatório (do cliente)" : "E-mails de Notificação"}
            value={machine.email_from_customer
              ? <>{emails.join(", ") || "—"}
                  <span className="text-muted" style={{ fontSize: 12 }}> — definidos pelo cliente, 1 e-mail por rodada</span></>
              : (emails.join(", ") || "—")} />
        </div>
      </div>

      {/* Coluna 2 — Status */}
      <div className="card" style={{ padding: "20px 24px" }}>
        <div style={cardTitleStyle}>
          <Wifi size={13} /> Status do Agente
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <InfoPill icon={<Wifi size={11} />} label="Conexão"
            value={<StatusBadge status={isAgentOnline ? "ONLINE" : (machine.active ? "OFFLINE" : "DESATIVADO")} />} />
          <InfoPill icon={<CalendarCheck size={11} />} label="Último contato"
            value={machine.last_seen ? fmtDate(machine.last_seen) : "Nunca"} />
          <InfoPill icon={<Clock size={11} />} label="Próximo contato (estimado)"
            value={isAgentOnline ? nextPingStr : "—"} />
          <InfoPill icon={<Archive size={11} />} label="Último Backup"
            value={<StatusBadge status={machine.last_backup_status} />} />
          <InfoPill icon={<CalendarCheck size={11} />} label="Data do Último Backup"
            value={fmtDate(machine.last_backup_at)} />
        </div>
      </div>

      {/* Coluna 3 — Saúde da Máquina (Telemetria) */}
      <div className="card" style={{ padding: "20px 24px" }}>
        <div style={cardTitleStyle}>
          <Network size={13} /> Saúde do Servidor
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {machine.telemetry ? (
            <>
              <TelemetryBar label="CPU" percent={machine.telemetry.cpu_percent || 0} info={`${machine.telemetry.cpu_percent || 0}%`} />
              <TelemetryBar label="RAM" percent={machine.telemetry.ram_percent || 0} info={`${machine.telemetry.ram_used_gb || 0} GB / ${machine.telemetry.ram_total_gb || 0} GB`} />
              {Array.isArray(machine.telemetry.disks) && machine.telemetry.disks.length > 0 ? (
                machine.telemetry.disks.map((d: { device?: string; mountpoint?: string; percent?: number; free_gb?: number; total_gb?: number }, i: number) => {
                  const label = d.device ? `Disco (${d.device})` : `Disco (${d.mountpoint || i})`;
                  const info = d.total_gb !== undefined ? `${d.free_gb ?? 0} GB Livre / ${d.total_gb ?? 0} GB` : `${d.free_gb ?? 0} GB Livre`;
                  return (
                    <TelemetryBar
                      key={d.mountpoint || d.device || i}
                      label={label}
                      percent={d.percent || 0}
                      info={info}
                    />
                  );
                })
              ) : (
                <TelemetryBar label="Disco (C:)" percent={machine.telemetry.disk_percent || 0} info={`${machine.telemetry.disk_free_gb || 0} GB Livre`} />
              )}
              {machine.telemetry.networks && machine.telemetry.networks.map((net: { name: string; mbps_sent?: number; mbps_recv?: number }, i: number) => (
                <TelemetryBar
                  key={i}
                  label={`Rede: ${net.name}`}
                  percent={Math.min(100, (((net.mbps_sent || 0) + (net.mbps_recv || 0)) / 1000) * 100)}
                  info={`↑ ${net.mbps_sent} Mbps  ↓ ${net.mbps_recv} Mbps`}
                />
              ))}
              {machine.telemetry.gpu_name && (
                <TelemetryBar label="GPU" percent={machine.telemetry.gpu_percent || 0} info={`${machine.telemetry.gpu_name} (${machine.telemetry.gpu_percent || 0}%)`} />
              )}
            </>
          ) : (
            <div style={{ fontSize: 13, color: "var(--text-muted)", fontStyle: "italic" }}>Sem dados de telemetria</div>
          )}
        </div>
      </div>
    </div>
  );
}
