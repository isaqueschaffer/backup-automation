import StatusBadge from "../../../components/StatusBadge";
import { DadosEquipamentos, WidgetInstancia } from "../types";

interface Props {
  dados: DadosEquipamentos;
  widget: WidgetInstancia;
}

export default function EquipamentosWidget({ dados }: Props) {
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
        Nenhum equipamento.
      </div>
    );
  }

  return (
    <div style={{ overflowX: "auto", minWidth: 0 }}>
      <table
        style={{
          width: "100%",
          minWidth: 320,
          borderCollapse: "collapse",
          fontSize: 12,
          textAlign: "left",
        }}
      >
        <thead>
          <tr
            style={{
              borderBottom: "1px solid var(--border)",
              color: "var(--text-secondary)",
              fontSize: 11,
            }}
          >
            <th style={{ padding: "4px 6px", whiteSpace: "nowrap" }}>Equipamento</th>
            <th style={{ padding: "4px 6px", whiteSpace: "nowrap" }}>Tipo</th>
            <th style={{ padding: "4px 6px", whiteSpace: "nowrap" }}>Máquina</th>
            <th style={{ padding: "4px 6px", textAlign: "right", whiteSpace: "nowrap" }}>Último backup</th>
          </tr>
        </thead>
        <tbody>
          {dados.equipamentos.map((eq) => (
            <tr
              key={eq.id}
              style={{
                borderBottom: "1px solid var(--border)",
              }}
            >
              <td
                style={{
                  padding: "6px",
                  fontWeight: 500,
                  color: "var(--text-primary)",
                  whiteSpace: "nowrap",
                }}
                title={eq.nome}
              >
                {eq.nome}
              </td>
              <td
                style={{
                  padding: "6px",
                  color: "var(--text-secondary)",
                  whiteSpace: "nowrap",
                }}
              >
                {eq.tipo}
              </td>
              <td
                style={{
                  padding: "6px",
                  color: "var(--text-secondary)",
                  whiteSpace: "nowrap",
                }}
                title={eq.maquina}
              >
                {eq.maquina}
              </td>
              <td style={{ padding: "6px", textAlign: "right", whiteSpace: "nowrap" }}>
                <StatusBadge status={eq.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
