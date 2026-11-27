import { ReactNode, useId, useState } from "react";
import { SlidersHorizontal } from "lucide-react";

// Barra de filtros que no celular fica atrás de um botão "Filtros (n)": antes os filtros ocupavam a primeira tela
// inteira. No computador a barra aparece sempre (o botão some pelo CSS).
export default function FiltrosRecolhiveis({ ativos, children, style }: {
  ativos: number; // quantos filtros estão diferentes do padrão
  children: ReactNode;
  style?: React.CSSProperties;
}) {
  const [aberto, setAberto] = useState(false);
  const id = useId();
  return (
    <div className={`filtros-recolhiveis${aberto ? " aberto" : ""}`}>
      <button
        type="button"
        className="btn btn-secondary filtros-botao"
        aria-expanded={aberto}
        aria-controls={id}
        onClick={() => setAberto(v => !v)}
      >
        <SlidersHorizontal size={15} /> {aberto ? "Esconder filtros" : "Filtros"}
        {ativos > 0 && <span className="filtros-contagem">{ativos}</span>}
      </button>
      <div id={id} className="filters-bar" style={{ flexWrap: "wrap", ...style }}>
        {children}
      </div>
    </div>
  );
}
