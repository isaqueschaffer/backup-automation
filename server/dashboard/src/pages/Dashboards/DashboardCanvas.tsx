import type { ReactNode } from "react";
import { DadosDashboard, DashboardLayout, WidgetInstancia } from "./types";
import WidgetFrame from "./WidgetFrame";

interface Props {
  layout: DashboardLayout;
  dados: DadosDashboard | null;
  renderAcoes?: (w: WidgetInstancia) => ReactNode;
}

export default function DashboardCanvas({ layout, dados, renderAcoes }: Props) {
  const widgets = layout?.widgets || [];

  if (widgets.length === 0) {
    return (
      <div
        className="card"
        style={{
          padding: 40,
          textAlign: "center",
          color: "var(--text-muted)",
          fontSize: 14,
        }}
      >
        Este dashboard ainda não tem componentes.
      </div>
    );
  }

  return (
    <div className="dash-grid">
      {widgets.map((w) => (
        <div
          className="dash-item"
          key={w.id}
          style={{
            gridColumn: `span ${w.largura}`,
            gridRow: `span ${w.altura}`,
          }}
        >
          <WidgetFrame
            widget={w}
            dados={dados?.widgets?.[w.id]}
            acoes={renderAcoes?.(w)}
          />
        </div>
      ))}
    </div>
  );
}
