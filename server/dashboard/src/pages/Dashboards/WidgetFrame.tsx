import type { ReactNode } from "react";
import { AlertCircle } from "lucide-react";
import { DadosWidget, WidgetInstancia } from "./types";
import { definicaoDe } from "./widgets/registry";

interface Props {
  widget: WidgetInstancia;
  dados?: DadosWidget;
  acoes?: ReactNode;
  children?: ReactNode;
}

export default function WidgetFrame({ widget, dados, acoes, children }: Props) {
  const def = definicaoDe(widget.tipo);
  const Icone = def?.icone || AlertCircle;
  const titulo = widget.titulo || def?.rotulo || "Widget";

  return (
    <div
      className="card"
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        padding: "12px 14px",
        minHeight: 0,
        minWidth: 0,
        boxSizing: "border-box",
      }}
    >
      {/* Cabeçalho do widget */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          marginBottom: 10,
          minHeight: 20,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 7,
            minWidth: 0,
            flex: 1,
          }}
        >
          <Icone
            size={16}
            style={{ color: "var(--accent)", flexShrink: 0 }}
          />
          <span
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: "var(--text-primary)",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
            title={titulo}
          >
            {titulo}
          </span>
        </div>

        {acoes && <div style={{ flexShrink: 0 }}>{acoes}</div>}
      </div>

      {/* Corpo do widget */}
      <div
        data-widget-corpo
        style={{
          flex: 1,
          minHeight: 0,
          minWidth: 0,
          overflow: "auto",
          overscrollBehavior: "contain",
        }}
      >
        {!def ? (
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
            Tipo de widget não disponível.
          </div>
        ) : dados === undefined ? (
          <div
            style={{
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <span className="spinner" />
          </div>
        ) : dados.ok === false ? (
          <div
            style={{
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
              color: "var(--text-muted)",
              fontSize: 12,
              padding: "0 8px",
              textAlign: "center",
            }}
          >
            <AlertCircle size={14} style={{ flexShrink: 0 }} />
            <span>{dados.erro || "Falha ao carregar dados do widget"}</span>
          </div>
        ) : children ? (
          children
        ) : (
          def.renderizar(dados.dados, widget)
        )}
      </div>
    </div>
  );
}
