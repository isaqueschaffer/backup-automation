import { Archive, Building2, CalendarCheck, Clock, KeyRound, Mail, Server, Wifi } from "lucide-react";
import { Machine } from "../../../../api/types";
import StatusBadge from "../../../../components/StatusBadge";
import { Link } from "react-router-dom";
import { fmtDate, fmtSchedule } from "../../../../utils/date";
import { cardTitleStyle } from "../utils";
import InfoPill from "./InfoPill";
import ServerHealthCard from "./ServerHealthCard";

// As três colunas do topo: Configuração, Status do Agente e Saúde do Servidor (telemetria)
export default function MachineInfoCards({ machine, customerEmails, isAgentOnline, nextPingStr, onCopy, nowMs }: {
  machine: Machine;
  // E-mails do cliente quando a máquina os herda (null = não carregados: usa os da máquina)
  customerEmails: string[] | null;
  isAgentOnline: boolean;
  nextPingStr: string;
  onCopy: (v: string) => void;
  nowMs: number;
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

      {/* Coluna 3 — Saúde do Servidor (telemetria) */}
      <ServerHealthCard
        telemetry={machine.telemetry}
        lastSeen={machine.last_seen}
        isAgentOnline={isAgentOnline}
        nowMs={nowMs}
        machineName={machine.name}
      />
    </div>
  );
}
