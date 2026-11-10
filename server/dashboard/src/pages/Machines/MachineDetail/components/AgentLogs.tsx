import { useEffect, useState } from "react";
import { Check, ChevronDown, ChevronRight, CloudLightning, Copy } from "lucide-react";
import { AgentLog } from "../../../../api/types";
import StatusBadge from "../../../../components/StatusBadge";
import { fmtDate } from "../../../../utils/date";

export type NivelFiltroLog = "todos" | "erro" | "aviso";

export interface FiltrosLogsState {
  mostrarPings: boolean;
  nivel: NivelFiltroLog;
  busca: string;
  equipamentoLog: string;
}

interface AgentLogsProps {
  logs: AgentLog[];
  filtros: FiltrosLogsState;
  onFiltrosChange: (novos: Partial<FiltrosLogsState>) => void;
  nomesEquipamentos: string[];
  podeVerMais: boolean;
  onVerMais: () => void;
  lastSeen: string | null;
  online?: boolean;
}

const TIPO_LABELS: Record<string, string> = {
  ping: "Ping",
  ping_recovery: "Reconectou",
  queue_backup: "Fila",
  queue_backup_skipped: "Fila ignorada",
  email_sent: "E-mail enviado",
  email_error: "Erro de e-mail",
  agent_log: "Agente",
};

function tipoStyle(tipo: string, nivel?: string): { background: string; color: string } {
  if (tipo === "agent_log") {
    if (nivel === "ERROR") {
      return { background: "rgba(239, 68, 68, 0.15)", color: "#ef4444" };
    }
    if (nivel === "WARNING") {
      return { background: "rgba(245, 158, 11, 0.15)", color: "#f59e0b" };
    }
    return { background: "rgba(59, 130, 246, 0.15)", color: "#3b82f6" };
  }
  if (tipo === "ping" || tipo === "email_sent") {
    return { background: "rgba(16, 185, 129, 0.15)", color: "#10b981" };
  }
  if (tipo === "email_error") {
    return { background: "rgba(239, 68, 68, 0.15)", color: "#ef4444" };
  }
  return { background: "rgba(59, 130, 246, 0.15)", color: "#3b82f6" };
}

export default function AgentLogs({
  logs,
  filtros,
  onFiltrosChange,
  nomesEquipamentos,
  podeVerMais,
  onVerMais,
  lastSeen,
  online,
}: AgentLogsProps) {
  const [aberta, setAberta] = useState(true);
  const [linhasExpandidas, setLinhasExpandidas] = useState<Set<string>>(new Set());
  const [copiadoId, setCopiadoId] = useState<string | null>(null);

  // Debounce do campo de busca (400 ms)
  const [buscaLocal, setBuscaLocal] = useState(filtros.busca);

  useEffect(() => {
    setBuscaLocal(filtros.busca);
  }, [filtros.busca]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (buscaLocal !== filtros.busca) {
        onFiltrosChange({ busca: buscaLocal });
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [buscaLocal, filtros.busca, onFiltrosChange]);

  const alternarLinha = (id: string) => {
    setLinhasExpandidas((prev) => {
      const prox = new Set(prev);
      if (prox.has(id)) prox.delete(id);
      else prox.add(id);
      return prox;
    });
  };

  const handleCopiar = async (texto: string, id: string) => {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiadoId(id);
      setTimeout(() => {
        setCopiadoId((prev) => (prev === id ? null : prev));
      }, 2000);
    } catch (e) {
      console.error("Falha ao copiar:", e);
    }
  };

  const temFiltroAtivo = Boolean(
    filtros.nivel !== "todos" ||
    (filtros.busca && filtros.busca.trim() !== "") ||
    (filtros.equipamentoLog && filtros.equipamentoLog.trim() !== "")
  );

  return (
    <div style={{ marginTop: 20 }}>
      <button
        type="button"
        aria-expanded={aberta}
        onClick={() => setAberta((v) => !v)}
        style={{
          width: "100%",
          background: "none",
          border: "none",
          padding: 0,
          margin: 0,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: 8,
          textAlign: "left",
          color: "inherit",
          font: "inherit",
        }}
      >
        {aberta ? (
          <ChevronDown size={15} style={{ flexShrink: 0, color: "var(--text-muted)" }} />
        ) : (
          <ChevronRight size={15} style={{ flexShrink: 0, color: "var(--text-muted)" }} />
        )}
        <CloudLightning size={15} style={{ flexShrink: 0, color: "var(--primary)" }} />
        <span style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>
          Eventos do Agente
        </span>
        <span
          style={{
            fontSize: 12,
            fontWeight: 600,
            padding: "2px 8px",
            borderRadius: 999,
            background: "rgba(255,255,255,0.06)",
            color: "var(--text-muted)",
          }}
        >
          {logs.length} eventos
        </span>

        <div
          style={{
            marginLeft: "auto",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          {online !== undefined && (
            <StatusBadge status={online ? "ONLINE" : "OFFLINE"} />
          )}
          <span className="text-xs text-muted">
            {lastSeen ? `Último ping: ${fmtDate(lastSeen)}` : "Sem ping ainda"}
          </span>
        </div>
      </button>

      {aberta && (
        <div style={{ marginTop: 12 }}>
          {/* Barra de Filtros */}
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              alignItems: "center",
              gap: 8,
              marginBottom: 12,
            }}
          >
            <select
              className="form-input"
              value={filtros.nivel}
              onChange={(e) => onFiltrosChange({ nivel: e.target.value as NivelFiltroLog })}
              title="Filtrar por nível"
              style={{ width: "auto", minWidth: 140, height: 34, fontSize: 12, padding: "4px 8px" }}
            >
              <option value="todos">Todos os níveis</option>
              <option value="erro">Só erros</option>
              <option value="aviso">Avisos e erros</option>
            </select>

            <select
              className="form-input"
              value={filtros.equipamentoLog}
              onChange={(e) => onFiltrosChange({ equipamentoLog: e.target.value })}
              title="Filtrar por equipamento"
              style={{ width: "auto", minWidth: 160, height: 34, fontSize: 12, padding: "4px 8px" }}
            >
              <option value="">Todos os equipamentos</option>
              {nomesEquipamentos.map((nome) => (
                <option key={nome} value={nome}>
                  {nome}
                </option>
              ))}
            </select>

            <input
              type="text"
              className="form-input"
              placeholder="Buscar no texto..."
              value={buscaLocal}
              onChange={(e) => setBuscaLocal(e.target.value)}
              style={{ flex: 1, minWidth: 160, height: 34, fontSize: 12, padding: "4px 8px" }}
            />

            <label
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontSize: 12,
                cursor: "pointer",
                userSelect: "none",
                color: "var(--text-secondary)",
                whiteSpace: "nowrap",
                paddingLeft: 4,
              }}
            >
              <input
                type="checkbox"
                checked={filtros.mostrarPings}
                onChange={(e) => onFiltrosChange({ mostrarPings: e.target.checked })}
                style={{ cursor: "pointer" }}
              />
              Mostrar pings
            </label>
          </div>

          {logs.length === 0 ? (
            <div className="empty-state" style={{ padding: 24 }}>
              {temFiltroAtivo
                ? "Nenhum evento com esses filtros."
                : filtros.mostrarPings
                ? "Nenhum evento registrado ainda. O agente deve enviar pings a cada 15 segundos."
                : "Nenhuma instrução ou erro recente. Marque “Mostrar pings” para ver também os pings."}
            </div>
          ) : (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 6,
                maxHeight: 460,
                overflowY: "auto",
                paddingRight: 6,
              }}
            >
              {logs.map((log) => {
                const label = TIPO_LABELS[log.event_type] || log.event_type;
                const colors = tipoStyle(log.event_type, log.nivel);
                const expandida = linhasExpandidas.has(log.id);
                const primeiraLinha = log.message.split("\n")[0] || "";

                return (
                  <div
                    key={log.id}
                    role="button"
                    tabIndex={0}
                    aria-expanded={expandida}
                    onClick={() => alternarLinha(log.id)}
                    onKeyDown={(e) => {
                      if (e.target !== e.currentTarget) return;
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        alternarLinha(log.id);
                      }
                    }}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "130px auto 1fr",
                      alignItems: expandida ? "start" : "center",
                      gap: 12,
                      background: "var(--surface-2, rgba(255,255,255,0.02))",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--radius-sm)",
                      padding: "8px 12px",
                      fontSize: 12,
                      cursor: "pointer",
                      transition: "border-color 0.15s ease, background 0.15s ease",
                    }}
                  >
                    <div style={{ fontWeight: 600, color: "var(--text-muted)", paddingTop: expandida ? 2 : 0 }}>
                      {fmtDate(log.created_at)}
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: 6, paddingTop: expandida ? 2 : 0 }}>
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 700,
                          textTransform: "uppercase",
                          padding: "2px 6px",
                          borderRadius: 4,
                          display: "inline-block",
                          whiteSpace: "nowrap",
                          background: colors.background,
                          color: colors.color,
                        }}
                      >
                        {label}
                      </span>
                      {log.nivel && log.nivel !== "INFO" && (
                        <span
                          style={{
                            fontSize: 10,
                            fontWeight: 700,
                            textTransform: "uppercase",
                            padding: "2px 6px",
                            borderRadius: 4,
                            display: "inline-block",
                            whiteSpace: "nowrap",
                            background:
                              log.nivel === "ERROR"
                                ? "rgba(239, 68, 68, 0.15)"
                                : "rgba(245, 158, 11, 0.15)",
                            color: log.nivel === "ERROR" ? "#ef4444" : "#f59e0b",
                          }}
                        >
                          {log.nivel}
                        </span>
                      )}
                    </div>

                    <div style={{ minWidth: 0 }}>
                      {!expandida ? (
                        <div
                          style={{
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            color: "var(--text-primary)",
                          }}
                        >
                          {log.equipamento && (
                            <span
                              style={{
                                fontSize: 10,
                                fontWeight: 600,
                                padding: "1px 6px",
                                borderRadius: 4,
                                background: "rgba(255,255,255,0.08)",
                                color: "var(--text-secondary)",
                                border: "1px solid var(--border)",
                                marginRight: 6,
                                display: "inline-block",
                              }}
                            >
                              {log.equipamento}
                            </span>
                          )}
                          <span>{primeiraLinha}</span>
                        </div>
                      ) : (
                        <div>
                          {log.equipamento && (
                            <div style={{ marginBottom: 6 }}>
                              <span
                                style={{
                                  fontSize: 10,
                                  fontWeight: 600,
                                  padding: "1px 6px",
                                  borderRadius: 4,
                                  background: "rgba(255,255,255,0.08)",
                                  color: "var(--text-secondary)",
                                  border: "1px solid var(--border)",
                                  display: "inline-block",
                                }}
                              >
                                {log.equipamento}
                              </span>
                            </div>
                          )}
                          <div
                            onClick={(e) => e.stopPropagation()}
                            style={{
                              fontFamily: "monospace, 'JetBrains Mono', 'Fira Code', Courier",
                              fontSize: 11,
                              lineHeight: 1.5,
                              whiteSpace: "pre-wrap",
                              wordBreak: "break-word",
                              maxHeight: 240,
                              overflowY: "auto",
                              background: "rgba(0, 0, 0, 0.3)",
                              border: "1px solid var(--border)",
                              borderRadius: 4,
                              padding: "8px 10px",
                              color: "var(--text-primary)",
                            }}
                          >
                            {log.message}
                          </div>
                          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 6 }}>
                            <button
                              type="button"
                              onKeyDown={(e) => e.stopPropagation()}
                              onClick={(e) => {
                                e.stopPropagation();
                                handleCopiar(log.message, log.id);
                              }}
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 4,
                                fontSize: 11,
                                fontWeight: 600,
                                padding: "3px 8px",
                                background: "var(--bg-elevated, rgba(255,255,255,0.06))",
                                border: "1px solid var(--border)",
                                borderRadius: "var(--radius-sm, 4px)",
                                color: copiadoId === log.id ? "var(--ok, #10b981)" : "var(--text-secondary)",
                                cursor: "pointer",
                              }}
                            >
                              {copiadoId === log.id ? (
                                <>
                                  <Check size={12} style={{ flexShrink: 0 }} />
                                  <span>Copiado</span>
                                </>
                              ) : (
                                <>
                                  <Copy size={12} style={{ flexShrink: 0 }} />
                                  <span>Copiar</span>
                                </>
                              )}
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}

              {podeVerMais && (
                <div style={{ display: "flex", justifyContent: "center", marginTop: 8, marginBottom: 4 }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={onVerMais}
                    style={{ fontSize: 12, padding: "6px 16px" }}
                  >
                    Ver mais
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
