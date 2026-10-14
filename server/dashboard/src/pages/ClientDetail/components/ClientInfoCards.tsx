import { Archive, Building2, CalendarCheck, Clock, KeyRound, Mail, Network, Server, Wifi } from "lucide-react";
import { Client } from "../../../api/types";
import StatusBadge from "../../../components/StatusBadge";
import { fmtDate } from "../../../utils/date";
import InfoPill from "./InfoPill";
import TelemetryBar from "./TelemetryBar";

const cardTitleStyle: React.CSSProperties = {
  fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.5px",
  color: "var(--text-muted)", marginBottom: 16, display: "flex", alignItems: "center", gap: 6,
};

// As três colunas do topo: Configuração, Status do Agente e Saúde do Servidor (telemetria)
export default function ClientInfoCards({ client, isAgentOnline, nextPingStr, onCopy }: {
  client: Client;
  isAgentOnline: boolean;
  nextPingStr: string;
  onCopy: (v: string) => void;
}) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16, marginBottom: 24 }}>

      {/* Coluna 1 — Configuração */}
      <div className="card" style={{ padding: "20px 24px" }}>
        <div style={cardTitleStyle}>
          <Server size={13} /> Configuração do Cliente
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <InfoPill icon={<KeyRound size={11} />} label="Client ID" value={client.id} mono copyValue={client.id} onCopy={onCopy} />
          <InfoPill icon={<KeyRound size={11} />} label="API Key (prefixo)" value={`${client.api_key_prefix}…`} mono />
          {client.group_name && (
            <InfoPill icon={<Building2 size={11} />} label="Unidade"
              value={`${client.group_name} (Posição ${(client.queue_order ?? 0) + 1} na fila)`} />
          )}
          <InfoPill icon={<Clock size={11} />} label="Horário do Backup"
            value={`${String(client.backup_hour).padStart(2, "0")}:${String(client.backup_minute).padStart(2, "0")} (diário)`} />
          <InfoPill icon={<Mail size={11} />} label="E-mails de Notificação"
            value={(client.email_to || []).join(", ") || "—"} />
        </div>
      </div>

      {/* Coluna 2 — Status */}
      <div className="card" style={{ padding: "20px 24px" }}>
        <div style={cardTitleStyle}>
          <Wifi size={13} /> Status do Agente
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <InfoPill icon={<Wifi size={11} />} label="Conexão"
            value={<StatusBadge status={isAgentOnline ? "ONLINE" : (client.active ? "OFFLINE" : "DESATIVADO")} />} />
          <InfoPill icon={<CalendarCheck size={11} />} label="Último contato"
            value={client.last_seen ? fmtDate(client.last_seen) : "Nunca"} />
          <InfoPill icon={<Clock size={11} />} label="Próximo contato (estimado)"
            value={isAgentOnline ? nextPingStr : "—"} />
          <InfoPill icon={<Archive size={11} />} label="Último Backup"
            value={<StatusBadge status={client.last_backup_status} />} />
          <InfoPill icon={<CalendarCheck size={11} />} label="Data do Último Backup"
            value={fmtDate(client.last_backup_at)} />
        </div>
      </div>

      {/* Coluna 3 — Saúde da Máquina (Telemetria) */}
      <div className="card" style={{ padding: "20px 24px" }}>
        <div style={cardTitleStyle}>
          <Network size={13} /> Saúde do Servidor
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {client.telemetry ? (
            <>
              <TelemetryBar label="CPU" percent={client.telemetry.cpu_percent || 0} info={`${client.telemetry.cpu_percent || 0}%`} />
              <TelemetryBar label="RAM" percent={client.telemetry.ram_percent || 0} info={`${client.telemetry.ram_used_gb || 0} GB / ${client.telemetry.ram_total_gb || 0} GB`} />
              <TelemetryBar label="Disco (C:)" percent={client.telemetry.disk_percent || 0} info={`${client.telemetry.disk_free_gb || 0} GB Livre`} />
              {client.telemetry.networks && client.telemetry.networks.map((net: { name: string; mbps_sent?: number; mbps_recv?: number }, i: number) => (
                <TelemetryBar
                  key={i}
                  label={`Rede: ${net.name}`}
                  percent={Math.min(100, (((net.mbps_sent || 0) + (net.mbps_recv || 0)) / 1000) * 100)}
                  info={`↑ ${net.mbps_sent} Mbps  ↓ ${net.mbps_recv} Mbps`}
                />
              ))}
              {client.telemetry.gpu_name && (
                <TelemetryBar label="GPU" percent={client.telemetry.gpu_percent || 0} info={`${client.telemetry.gpu_name} (${client.telemetry.gpu_percent || 0}%)`} />
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
