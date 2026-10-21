import { GripVertical, Settings, Trash2 } from "lucide-react";
import { Altura, Largura, WidgetInstancia } from "./types";
import { LARGURAS } from "./widgets/registry";

interface Props {
  widget: WidgetInstancia;
  onLargura: (l: Largura) => void;
  onAltura: (a: Altura) => void;
  onConfigurar: () => void;
  onRemover: () => void;
}

// Barra de controle de um componente no modo de edição do dashboard
export default function WidgetAcoesEdicao({
  widget,
  onLargura,
  onAltura,
  onConfigurar,
  onRemover,
}: Props) {
  return (
    <div
      style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}
      onClick={(e) => e.stopPropagation()}
    >
      <span
        data-drag-handle
        title="Arraste para reordenar"
        style={{
          cursor: "grab",
          display: "inline-flex",
          alignItems: "center",
          padding: "2px 2px",
          color: "var(--text-secondary)",
          flexShrink: 0,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <GripVertical size={15} style={{ flexShrink: 0 }} />
      </span>

      <select
        value={widget.largura}
        title="Largura"
        onChange={(e) => {
          e.stopPropagation();
          onLargura(Number(e.target.value) as Largura);
        }}
        onClick={(e) => e.stopPropagation()}
        style={{
          fontSize: 11,
          padding: "2px 4px",
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
          color: "var(--text-primary)",
          borderRadius: 6,
          cursor: "pointer",
          flexShrink: 0,
        }}
      >
        {LARGURAS.map((item) => (
          <option key={item.valor} value={item.valor}>
            {item.rotulo}
          </option>
        ))}
      </select>

      <select
        value={widget.altura}
        title="Altura"
        onChange={(e) => {
          e.stopPropagation();
          onAltura(Number(e.target.value) as Altura);
        }}
        onClick={(e) => e.stopPropagation()}
        style={{
          fontSize: 11,
          padding: "2px 4px",
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
          color: "var(--text-primary)",
          borderRadius: 6,
          cursor: "pointer",
          flexShrink: 0,
        }}
      >
        <option value={1}>1 linha</option>
        <option value={2}>2 linhas</option>
        <option value={3}>3 linhas</option>
        <option value={4}>4 linhas</option>
      </select>

      <button
        type="button"
        className="btn-icon"
        title="Configurar componente"
        style={{ width: 26, height: 26, flexShrink: 0 }}
        onClick={(e) => {
          e.stopPropagation();
          onConfigurar();
        }}
      >
        <Settings size={14} style={{ flexShrink: 0 }} />
      </button>

      <button
        type="button"
        className="btn-icon"
        title="Remover componente"
        style={{ width: 26, height: 26, color: "var(--err)", flexShrink: 0 }}
        onClick={(e) => {
          e.stopPropagation();
          onRemover();
        }}
      >
        <Trash2 size={14} style={{ flexShrink: 0 }} />
      </button>
    </div>
  );
}
