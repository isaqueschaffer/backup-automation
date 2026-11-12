import Modal from "../../components/Modal";
import { DEFINICOES, DefinicaoWidget } from "./widgets/registry";

interface Props {
  onEscolher: (def: DefinicaoWidget) => void;
  onClose: () => void;
}

// Modal de seleção para adicionar um novo componente ao dashboard
export default function AddWidgetModal({ onEscolher, onClose }: Props) {
  const lista = Object.values(DEFINICOES);

  return (
    <Modal title="Adicionar componente" onClose={onClose} width={640}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
          gap: 12,
          maxHeight: "65vh",
          overflowY: "auto",
          padding: "4px 2px",
        }}
      >
        {lista.map((def) => {
          const Icone = def.icone;
          return (
            <button
              key={def.tipo}
              type="button"
              onClick={() => onEscolher(def)}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 12,
                padding: "12px 14px",
                borderRadius: "var(--radius-sm, 8px)",
                background: "var(--surface)",
                border: "1px solid var(--border)",
                textAlign: "left",
                cursor: "pointer",
                transition: "border-color 0.15s ease",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = "var(--accent)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = "var(--border)";
              }}
            >
              <div
                style={{
                  padding: 8,
                  borderRadius: 8,
                  background: "var(--surface-2)",
                  color: "var(--accent)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                <Icone size={20} style={{ flexShrink: 0 }} />
              </div>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div
                  style={{
                    fontWeight: 600,
                    fontSize: 14,
                    color: "var(--text-primary)",
                    marginBottom: 2,
                  }}
                >
                  {def.rotulo}
                </div>
                <div
                  style={{
                    fontSize: 12,
                    color: "var(--text-muted)",
                    lineHeight: 1.4,
                  }}
                >
                  {def.descricao}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </Modal>
  );
}
