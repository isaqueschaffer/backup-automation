import StatusBadge from "../../../components/StatusBadge";
import { fmtDate } from "../../../utils/date";
import { DadosStatusBackups, WidgetInstancia } from "../types";

interface Props {
  dados: DadosStatusBackups;
  widget: WidgetInstancia;
}

function dotStatus(s: string | null | undefined): string {
  if (!s) return "muted";
  const st = s.toUpperCase();
  if (st === "OK" || st === "ONLINE" || st === "COM_GRAVACAO" || st === "SEM_ARQUIVOS") return "ok";
  if (st === "PARTIAL" || st === "PARCIAL" || st === "SEM_GRAVACAO" || st === "EM_ANDAMENTO") return "warn";
  if (st === "OFFLINE" || st === "ERROR" || st === "ERRO" || st === "ERRO_COMUNICACAO" || st === "NAO_EXECUTOU") return "err";
  return "muted";
}

export default function StatusBackupsWidget({ dados }: Props) {
  if (!dados.maquinas || dados.maquinas.length === 0) {
    return (
      <div
        style={{
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text-muted)",
          fontSize: 12,
        }}
      >
        Nenhuma máquina encontrada.
      </div>
    );
  }

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
    >
      {dados.maquinas.map((m) => (
        <div
          key={m.id}
          style={{
            backgroundColor: "var(--surface-2)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            padding: "8px 10px",
            display: "flex",
            flexDirection: "column",
            gap: 6,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 8,
              flexWrap: "wrap",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                minWidth: 0,
                flexWrap: "wrap",
              }}
            >
              <span
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: "var(--text-primary)",
                }}
              >
                {m.nome}
              </span>
              <span
                style={{
                  fontSize: 11,
                  color: "var(--text-muted)",
                  whiteSpace: "nowrap",
                }}
              >
                · Último: {fmtDate(m.ultimo_backup, { short: true, empty: "nunca" })}
              </span>
            </div>
            <div style={{ flexShrink: 0 }}>
              <StatusBadge status={m.status} />
            </div>
          </div>

          {m.equipamentos && m.equipamentos.length > 0 && (
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 5,
                marginTop: 2,
              }}
            >
              {m.equipamentos.map((e, idx) => (
                <span
                  key={`${e.nome}-${idx}`}
                  title={`${e.tipo}: ${e.status || "Sem dados"}`}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 5,
                    backgroundColor: "var(--surface)",
                    border: "1px solid var(--border)",
                    borderRadius: 4,
                    padding: "2px 6px",
                    fontSize: 11,
                    color: "var(--text-secondary)",
                  }}
                >
                  <span
                    className={`dot ${dotStatus(e.status)}`}
                    style={{ flexShrink: 0 }}
                  />
                  <span
                    style={{
                      maxWidth: 120,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {e.nome}
                  </span>
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
