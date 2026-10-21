import StatusBadge from "../../../components/StatusBadge";
import { DadosCameras, WidgetInstancia } from "../types";

interface Props {
  dados: DadosCameras;
  widget: WidgetInstancia;
}

export default function CamerasWidget({ dados }: Props) {
  if (!dados.equipamentos || dados.equipamentos.length === 0) {
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
        Nenhum equipamento com câmeras.
      </div>
    );
  }

  return (
    <div
      style={{
        height: "100%",
        overflow: "auto",
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      {dados.equipamentos.map((eq) => {
        const total = eq.total || 0;
        const onlinePct = total > 0 ? (eq.online / total) * 100 : 0;
        const offlinePct = total > 0 ? (eq.offline / total) * 100 : 0;

        const problemas = (eq.cameras || []).filter(
          (c) => c.comunicacao !== "ONLINE" || c.gravacao === "SEM_GRAVACAO"
        );

        return (
          <div
            key={eq.id}
            style={{
              backgroundColor: "var(--surface-2)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: "10px 12px",
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            {/* Cabeçalho do equipamento */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 8,
                flexWrap: "wrap",
              }}
            >
              <div style={{ minWidth: 0 }}>
                <span
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: "var(--text-primary)",
                  }}
                >
                  {eq.nome}
                </span>
                <span
                  style={{
                    fontSize: 11,
                    color: "var(--text-muted)",
                    marginLeft: 6,
                  }}
                >
                  · {eq.maquina}
                </span>
              </div>

              {/* Contadores */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  fontSize: 11,
                }}
              >
                <span style={{ color: "var(--ok)", fontWeight: 600 }}>
                  {eq.online} online
                </span>
                {eq.offline > 0 && (
                  <span style={{ color: "var(--err)", fontWeight: 600 }}>
                    {eq.offline} offline
                  </span>
                )}
                {eq.sem_gravacao > 0 && (
                  <span style={{ color: "var(--warn)", fontWeight: 600 }}>
                    {eq.sem_gravacao} s/ gravação
                  </span>
                )}
              </div>
            </div>

            {/* Barra de proporção */}
            <div
              style={{
                width: "100%",
                height: 4,
                backgroundColor: "var(--border)",
                borderRadius: 2,
                overflow: "hidden",
                display: "flex",
              }}
            >
              {onlinePct > 0 && (
                <div
                  style={{
                    width: `${onlinePct}%`,
                    backgroundColor: "var(--ok)",
                    height: "100%",
                  }}
                />
              )}
              {offlinePct > 0 && (
                <div
                  style={{
                    width: `${offlinePct}%`,
                    backgroundColor: "var(--err)",
                    height: "100%",
                  }}
                />
              )}
            </div>

            {/* Câmeras com problemas ou sucesso */}
            {problemas.length === 0 ? (
              <div
                style={{
                  fontSize: 11,
                  color: "var(--ok)",
                  fontStyle: "italic",
                }}
              >
                Todas as câmeras online e gravando
              </div>
            ) : (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 4,
                  marginTop: 2,
                }}
              >
                {problemas.map((cam, idx) => (
                  <div
                    key={`${cam.nome}-${idx}`}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 8,
                      fontSize: 11,
                      padding: "2px 0",
                    }}
                  >
                    <span
                      style={{
                        color: "var(--text-secondary)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      title={cam.nome}
                    >
                      {cam.nome}
                    </span>
                    <StatusBadge
                      status={
                        cam.comunicacao !== "ONLINE"
                          ? "OFFLINE"
                          : "SEM_GRAVACAO"
                      }
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
