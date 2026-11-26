import { CSSProperties, ReactNode, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { MoreHorizontal } from "lucide-react";

export interface AcaoMenu {
  rotulo: string;
  icone?: ReactNode;
  onClick: () => void;
  perigo?: boolean;       // ações que apagam ou invalidam algo: vermelho e separadas das demais
  desabilitada?: boolean;
  dica?: string;
}

// Menu "Mais ações": guarda as ações raras ou perigosas fora da fileira de botões comuns.
// Fecha com Esc, clique fora, rolagem ou ao escolher; as setas andam entre os itens.
// A lista usa posição fixa (calculada do botão): dentro de uma tabela com rolagem (.table-wrap) ela seria cortada.
export default function MenuAcoes({ acoes, rotulo = "Mais ações", alinhar = "direita", compacto = false }: {
  acoes: AcaoMenu[];
  rotulo?: string;
  alinhar?: "direita" | "esquerda";
  compacto?: boolean; // só o ícone (linhas e cards), com o rótulo no title/aria-label
}) {
  const [aberto, setAberto] = useState(false);
  const raiz = useRef<HTMLDivElement>(null);
  const idMenu = useId();
  const [pos, setPos] = useState<CSSProperties>({});

  useLayoutEffect(() => {
    if (!aberto) return;
    const botao = raiz.current?.querySelector<HTMLButtonElement>("button[aria-haspopup]");
    const lista = raiz.current?.querySelector<HTMLDivElement>('[role="menu"]');
    if (!botao || !lista) return;
    const r = botao.getBoundingClientRect();
    const alt = lista.offsetHeight;
    const larg = lista.offsetWidth;
    const embaixo = r.bottom + 6 + alt <= window.innerHeight || r.top - 6 - alt < 0;
    let left = alinhar === "esquerda" ? r.left : r.right - larg;
    left = Math.max(8, Math.min(left, window.innerWidth - larg - 8));
    setPos({ position: "fixed", left, top: embaixo ? r.bottom + 6 : r.top - 6 - alt, right: "auto" });
  }, [aberto, alinhar]);

  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => {
      if (raiz.current && !raiz.current.contains(e.target as Node)) setAberto(false);
    };
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setAberto(false);
        raiz.current?.querySelector<HTMLButtonElement>("button[aria-haspopup]")?.focus();
      }
    };
    const fechar = () => setAberto(false);
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", tecla);
    window.addEventListener("scroll", fechar, true);
    window.addEventListener("resize", fechar);
    raiz.current?.querySelector<HTMLButtonElement>('[role="menuitem"]:not(:disabled)')?.focus();
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", tecla);
      window.removeEventListener("scroll", fechar, true);
      window.removeEventListener("resize", fechar);
    };
  }, [aberto]);

  const comuns = acoes.filter(a => !a.perigo);
  const perigosas = acoes.filter(a => a.perigo);

  const andar = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const itens = Array.from(raiz.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') ?? []);
    const i = itens.indexOf(document.activeElement as HTMLButtonElement);
    const prox = e.key === "ArrowDown" ? (i + 1) % itens.length : (i - 1 + itens.length) % itens.length;
    itens[prox]?.focus();
  };

  const item = (a: AcaoMenu) => (
    <button
      key={a.rotulo}
      type="button"
      role="menuitem"
      className={`menu-acoes-item${a.perigo ? " perigo" : ""}`}
      disabled={a.desabilitada}
      title={a.dica}
      onClick={(e) => {
        e.stopPropagation();
        setAberto(false);
        a.onClick();
      }}
    >
      {a.icone}
      {a.rotulo}
    </button>
  );

  if (acoes.length === 0) return null;

  return (
    <div className="menu-acoes" ref={raiz} onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        className={compacto ? "btn-icon" : "btn btn-secondary"}
        aria-haspopup="menu"
        aria-expanded={aberto}
        aria-controls={aberto ? idMenu : undefined}
        aria-label={compacto ? rotulo : undefined}
        title={compacto ? rotulo : undefined}
        onClick={() => setAberto(v => !v)}
      >
        <MoreHorizontal size={15} />{!compacto && <> {rotulo}</>}
      </button>
      {aberto && (
        <div
          id={idMenu}
          role="menu"
          className="menu-acoes-lista"
          style={pos}
          onKeyDown={andar}
        >
          {comuns.map(item)}
          {comuns.length > 0 && perigosas.length > 0 && <div className="menu-acoes-sep" role="separator" />}
          {perigosas.map(item)}
        </div>
      )}
    </div>
  );
}
