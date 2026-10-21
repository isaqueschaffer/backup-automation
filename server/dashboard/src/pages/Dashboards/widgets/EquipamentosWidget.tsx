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
    <div style={{ height: "100%", overflow: "auto" }}>
      <table
        style={{
          width: "100%",
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
            <th style={{ padding: "4px 6px" }}>Equipamento</th>
            <th style={{ padding: "4px 6px" }}>Tipo</th>
            <th style={{ padding: "4px 6px" }}>Máquina</th>
            <th style={{ padding: "4px 6px", textAlign: "right" }}>Último backup</th>
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
                }}
              >
                {eq.nome}
              </td>
              <td
                style={{
                  padding: "6px",
                  color: "var(--text-secondary)",
                }}
              >
                {eq.tipo}
              </td>
              <td
                style={{
                  padding: "6px",
                  color: "var(--text-secondary)",
                }}
              >
                {eq.maquina}
              </td>
              <td style={{ padding: "6px", textAlign: "right" }}>
                <StatusBadge status={eq.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
