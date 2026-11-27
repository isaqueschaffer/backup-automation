import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent, ReactNode } from "react";
import {
  ALTURA_LINHA_PX,
  ALTURA_MAX_GRADE,
  COLUNAS_GRADE,
  DadosDashboard,
  DashboardLayout,
  RESPIRO_GRADE_PX,
  WidgetInstancia,
} from "./types";
import { definicaoDe } from "./widgets/registry";
import { linhasDoConteudo } from "./medirConteudo";
import { Caixa, fundoDaGrade, mesmasPosicoes, ordenarPorPosicao, posicionar } from "./gradeLayout";
import WidgetFrame from "./WidgetFrame";

interface Props {
  layout: DashboardLayout;
  dados: DadosDashboard | null;
  renderAcoes?: (w: WidgetInstancia) => ReactNode;
  editando?: boolean;
  // Recebe o layout inteiro ao soltar um arrasto ou redimensionamento (um passo do desfazer)
  onAlterar?: (widgets: WidgetInstancia[]) => void;
  onAjustar?: (id: string) => void;
}

type Eixo = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

interface Gesto {
  tipo: "mover" | "redimensionar";
  id: string;
  eixo: Eixo | null;
  // Posição do ponteiro relativa à grade no início (acompanha a rolagem da página)
  inicioX: number;
  inicioY: number;
  base: WidgetInstancia[];
  original: WidgetInstancia;
  minL: number;
  minA: number;
  ativo: boolean;
  ultimoX: number;
  ultimoY: number;
}

interface Previa {
  tipo: "mover" | "redimensionar";
  id: string;
  widgets: WidgetInstancia[];
  original: WidgetInstancia;
  dx: number;
  dy: number;
}

const LIMIAR_ARRASTO_PX = 4;
const BORDA_AUTOROLAGEM_PX = 56;
const LINHAS_EXTRAS_EDICAO = 6;
const TELA_ESTREITA = "(max-width: 1000px)";

const limitar = (v: number, min: number, max: number) => Math.max(min, Math.min(max, v));

function useTelaEstreita(): boolean {
  const [estreita, setEstreita] = useState(
    () => typeof window !== "undefined" && window.matchMedia(TELA_ESTREITA).matches
  );
  useEffect(() => {
    const m = window.matchMedia(TELA_ESTREITA);
    const aoMudar = () => setEstreita(m.matches);
    aoMudar();
    m.addEventListener("change", aoMudar);
    return () => m.removeEventListener("change", aoMudar);
  }, []);
  return estreita;
}

const ALCAS: { eixo: Eixo; estilo: CSSProperties; cursor: string; titulo: string }[] = [
  { eixo: "n", cursor: "ns-resize", titulo: "Arraste para alterar a altura", estilo: { top: -5, left: 14, right: 14, height: 10 } },
  { eixo: "s", cursor: "ns-resize", titulo: "Arraste para alterar a altura (dois cliques ajustam ao conteúdo)", estilo: { bottom: -5, left: 14, right: 14, height: 10 } },
  { eixo: "w", cursor: "ew-resize", titulo: "Arraste para alterar a largura", estilo: { left: -5, top: 14, bottom: 14, width: 10 } },
  { eixo: "e", cursor: "ew-resize", titulo: "Arraste para alterar a largura", estilo: { right: -5, top: 14, bottom: 14, width: 10 } },
  { eixo: "nw", cursor: "nwse-resize", titulo: "Arraste para redimensionar", estilo: { top: -5, left: -5, width: 16, height: 16 } },
  { eixo: "ne", cursor: "nesw-resize", titulo: "Arraste para redimensionar", estilo: { top: -5, right: -5, width: 16, height: 16 } },
  { eixo: "sw", cursor: "nesw-resize", titulo: "Arraste para redimensionar", estilo: { bottom: -5, left: -5, width: 16, height: 16 } },
  { eixo: "se", cursor: "nwse-resize", titulo: "Arraste para redimensionar (dois cliques ajustam ao conteúdo)", estilo: { bottom: -3, right: -3, width: 16, height: 16 } },
];

// Grade livre do dashboard: arrastar pelo cabeçalho para qualquer lugar e redimensionar pelos
// quatro lados e cantos. Os outros componentes abrem espaço e sobem para tapar buracos.
export default function DashboardCanvas({
  layout,
  dados,
  renderAcoes,
  editando,
  onAlterar,
  onAjustar,
}: Props) {
  const widgets = useMemo(() => layout?.widgets || [], [layout]);
  const telaEstreita = useTelaEstreita();

  const [larguraGrade, setLarguraGrade] = useState(0);
  const gradeRef = useRef<HTMLDivElement | null>(null);
  const observadorRef = useRef<ResizeObserver | null>(null);
  const refGrade = useCallback((el: HTMLDivElement | null) => {
    observadorRef.current?.disconnect();
    observadorRef.current = null;
    gradeRef.current = el;
    if (!el) return;
    setLarguraGrade(el.getBoundingClientRect().width);
    if (typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver(([entrada]) => {
        if (entrada) setLarguraGrade(entrada.contentRect.width);
      });
      ro.observe(el);
      observadorRef.current = ro;
    }
  }, []);

  const larguraColuna = larguraGrade / COLUNAS_GRADE;

  const [previa, setPrevia] = useState<Previa | null>(null);
  const previaRef = useRef<Previa | null>(null);
  const gestoRef = useRef<Gesto | null>(null);
  const autoRolagemRef = useRef<number | null>(null);
  const colunaRef = useRef(larguraColuna);
  colunaRef.current = larguraColuna;
  const onAlterarRef = useRef(onAlterar);
  onAlterarRef.current = onAlterar;

  const pontoNaGrade = (clientX: number, clientY: number) => {
    const r = gradeRef.current?.getBoundingClientRect();
    return { x: clientX - (r?.left ?? 0), y: clientY - (r?.top ?? 0) };
  };

  const atualizarGesto = useCallback(() => {
    const g = gestoRef.current;
    if (!g) return;
    const p = pontoNaGrade(g.ultimoX, g.ultimoY);
    const dx = p.x - g.inicioX;
    const dy = p.y - g.inicioY;

    if (!g.ativo) {
      if (Math.hypot(dx, dy) < LIMIAR_ARRASTO_PX) return;
      g.ativo = true;
      document.body.classList.add(g.tipo === "mover" ? "dash-arrastando" : "dash-resizing");
    }

    const cw = colunaRef.current > 0 ? colunaRef.current : 1;
    const o = g.original;
    let caixa: Caixa;
    if (g.tipo === "mover") {
      caixa = { x: o.x + dx / cw, y: o.y + dy / ALTURA_LINHA_PX, largura: o.largura, altura: o.altura };
    } else {
      const eixo = g.eixo || "se";
      const px = Math.round(dx / cw);
      const py = Math.round(dy / ALTURA_LINHA_PX);
      let { x, y, largura, altura } = o;
      if (eixo.includes("e")) largura = limitar(o.largura + px, g.minL, COLUNAS_GRADE - o.x);
      if (eixo.includes("w")) {
        const d = limitar(px, -o.x, o.largura - g.minL);
        x = o.x + d;
        largura = o.largura - d;
      }
      if (eixo.includes("s")) altura = limitar(o.altura + py, g.minA, ALTURA_MAX_GRADE);
      if (eixo.includes("n")) {
        const d = limitar(py, -o.y, o.altura - g.minA);
        y = o.y + d;
        altura = o.altura - d;
      }
      caixa = { x, y, largura, altura };
    }

    const nova: Previa = {
      tipo: g.tipo,
      id: g.id,
      widgets: posicionar(g.base, g.id, caixa),
      original: o,
      dx,
      dy,
    };
    previaRef.current = nova;
    setPrevia(nova);
  }, []);

  const pararAutoRolagem = () => {
    if (autoRolagemRef.current !== null) {
      cancelAnimationFrame(autoRolagemRef.current);
      autoRolagemRef.current = null;
    }
  };

  // Rola a página enquanto o ponteiro estiver perto da borda de cima ou de baixo da janela
  const autoRolar = useCallback(() => {
    const g = gestoRef.current;
    if (!g || !g.ativo) {
      autoRolagemRef.current = null;
      return;
    }
    const y = g.ultimoY;
    let passo = 0;
    if (y < BORDA_AUTOROLAGEM_PX) passo = -Math.ceil((BORDA_AUTOROLAGEM_PX - y) / 4);
    else if (y > window.innerHeight - BORDA_AUTOROLAGEM_PX)
      passo = Math.ceil((y - (window.innerHeight - BORDA_AUTOROLAGEM_PX)) / 4);
    if (passo === 0) {
      autoRolagemRef.current = null;
      return;
    }
    window.scrollBy(0, passo);
    atualizarGesto();
    autoRolagemRef.current = requestAnimationFrame(autoRolar);
  }, [atualizarGesto]);

  const aoMoverPonteiro = useCallback(
    (e: PointerEvent) => {
      const g = gestoRef.current;
      if (!g) return;
      g.ultimoX = e.clientX;
      g.ultimoY = e.clientY;
      atualizarGesto();
      if (g.ativo && autoRolagemRef.current === null) {
        autoRolagemRef.current = requestAnimationFrame(autoRolar);
      }
    },
    [atualizarGesto, autoRolar]
  );

  const aoRolar = useCallback(() => {
    if (gestoRef.current?.ativo) atualizarGesto();
  }, [atualizarGesto]);

  const aoSoltar = useCallback(() => {
    const g = gestoRef.current;
    const p = previaRef.current;
    gestoRef.current = null;
    previaRef.current = null;
    pararAutoRolagem();
    window.removeEventListener("pointermove", aoMoverPonteiro);
    window.removeEventListener("pointerup", aoSoltar);
    window.removeEventListener("pointercancel", aoSoltar);
    window.removeEventListener("scroll", aoRolar, true);
    document.body.classList.remove("dash-arrastando", "dash-resizing");
    setPrevia(null);
    if (g?.ativo && p && !mesmasPosicoes(p.widgets, g.base)) {
      onAlterarRef.current?.(p.widgets);
    }
  }, [aoMoverPonteiro, aoRolar]);

  // Limpa ouvintes e classes se o componente sair da tela no meio de um gesto
  useEffect(() => {
    return () => {
      pararAutoRolagem();
      window.removeEventListener("pointermove", aoMoverPonteiro);
      window.removeEventListener("pointerup", aoSoltar);
      window.removeEventListener("pointercancel", aoSoltar);
      window.removeEventListener("scroll", aoRolar, true);
      document.body.classList.remove("dash-arrastando", "dash-resizing");
    };
  }, [aoMoverPonteiro, aoSoltar, aoRolar]);

  const iniciarGesto = (
    e: ReactPointerEvent<HTMLElement>,
    w: WidgetInstancia,
    tipo: "mover" | "redimensionar",
    eixo: Eixo | null
  ) => {
    if (gestoRef.current) return;
    const def = definicaoDe(w.tipo);
    const minL = Math.max(1, def?.larguraMin ?? 2);
    let minA = Math.max(1, def?.alturaMin ?? 2);
    if (tipo === "redimensionar" && !def?.alturaFluida) {
      const item = (e.currentTarget as HTMLElement).closest<HTMLElement>("[data-widget-id]");
      const cabe = item ? linhasDoConteudo(item) : null;
      if (cabe !== null) minA = Math.max(1, Math.min(minA, cabe));
    }
    const p = pontoNaGrade(e.clientX, e.clientY);
    gestoRef.current = {
      tipo,
      id: w.id,
      eixo,
      inicioX: p.x,
      inicioY: p.y,
      base: widgets,
      original: w,
      minL,
      minA,
      ativo: false,
      ultimoX: e.clientX,
      ultimoY: e.clientY,
    };
    window.addEventListener("pointermove", aoMoverPonteiro);
    window.addEventListener("pointerup", aoSoltar);
    window.addEventListener("pointercancel", aoSoltar);
    window.addEventListener("scroll", aoRolar, true);
  };

  const podeEditarGrade = Boolean(editando && onAlterar) && !telaEstreita;

  const aoPressionarItem = (e: ReactPointerEvent<HTMLDivElement>, w: WidgetInstancia) => {
    if (!podeEditarGrade || e.button !== 0) return;
    const alvo = e.target as HTMLElement;
    if (!alvo.closest("[data-drag-handle]")) return;
    if (alvo.closest("button, a, input, select, textarea, label")) return;
    e.preventDefault();
    iniciarGesto(e, w, "mover", null);
  };

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
        {editando
          ? "Nenhum componente. Use “Adicionar componente”."
          : "Este dashboard ainda não tem componentes."}
      </div>
    );
  }

  // Tela estreita (celular/tablet): componentes empilhados na ordem de leitura, sem arrastar
  if (telaEstreita) {
    return (
      <div className="dash-grid">
        {ordenarPorPosicao(widgets).map((w) => (
          <div
            className="dash-item"
            key={w.id}
            data-widget-id={w.id}
            style={{
              minWidth: 0,
              borderRadius: 8,
              outline: editando ? "1px dashed var(--border-accent)" : undefined,
            }}
          >
            <WidgetFrame widget={w} dados={dados?.widgets?.[w.id]} acoes={renderAcoes?.(w)} />
          </div>
        ))}
      </div>
    );
  }

  const exibidos = previa?.widgets ?? widgets;
  const posicaoPorId = new Map(exibidos.map((w) => [w.id, w]));
  const linhas = fundoDaGrade(exibidos) + (editando ? LINHAS_EXTRAS_EDICAO : 0);
  const animar = Boolean(editando && larguraGrade > 0);
  // Ordem estável no DOM (por id) para as transições não reiniciarem quando a ordem muda
  const estaveis = [...widgets].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));

  return (
    <div
      ref={refGrade}
      className={editando ? "dash-grade dash-grade-guia" : "dash-grade"}
      style={{
        position: "relative",
        margin: -RESPIRO_GRADE_PX,
        height: linhas * ALTURA_LINHA_PX,
        // Pontos nos cantos das células, para mostrar onde o componente pode encaixar
        backgroundSize: editando ? `${larguraColuna}px ${ALTURA_LINHA_PX}px` : undefined,
        backgroundPosition: editando
          ? `${-larguraColuna / 2}px ${-ALTURA_LINHA_PX / 2}px`
          : undefined,
      }}
    >
      {/* Lugar onde o componente arrastado vai cair */}
      {previa?.tipo === "mover" &&
        (() => {
          const c = posicaoPorId.get(previa.id);
          if (!c) return null;
          return (
            <div
              aria-hidden
              style={{
                position: "absolute",
                left: c.x * larguraColuna + RESPIRO_GRADE_PX,
                top: c.y * ALTURA_LINHA_PX + RESPIRO_GRADE_PX,
                width: c.largura * larguraColuna - 2 * RESPIRO_GRADE_PX,
                height: c.altura * ALTURA_LINHA_PX - 2 * RESPIRO_GRADE_PX,
                borderRadius: 8,
                border: "2px dashed var(--accent)",
                background: "var(--accent-glow)",
                transition: "left .15s ease, top .15s ease",
                pointerEvents: "none",
              }}
            />
          );
        })()}

      {estaveis.map((w) => {
        const c = posicaoPorId.get(w.id) ?? w;
        const arrastando = previa?.tipo === "mover" && previa.id === w.id;
        const redimensionando = previa?.tipo === "redimensionar" && previa.id === w.id;

        let left = c.x * larguraColuna;
        let top = c.y * ALTURA_LINHA_PX;
        let width = c.largura * larguraColuna;
        let height = c.altura * ALTURA_LINHA_PX;
        if (arrastando && previa) {
          const o = previa.original;
          left = o.x * larguraColuna + previa.dx;
          top = o.y * ALTURA_LINHA_PX + previa.dy;
          width = o.largura * larguraColuna;
          height = o.altura * ALTURA_LINHA_PX;
        }

        return (
          <div
            key={w.id}
            data-widget-id={w.id}
            onPointerDown={(e) => aoPressionarItem(e, w)}
            style={{
              position: "absolute",
              left,
              top,
              width,
              height,
              padding: RESPIRO_GRADE_PX,
              boxSizing: "border-box",
              minWidth: 0,
              zIndex: arrastando ? 30 : redimensionando ? 20 : undefined,
              transition:
                animar && !arrastando && !redimensionando
                  ? "left .18s ease, top .18s ease, width .18s ease, height .18s ease"
                  : "none",
            }}
          >
            <div
              style={{
                position: "relative",
                height: "100%",
                borderRadius: 8,
                opacity: arrastando ? 0.92 : 1,
                boxShadow: arrastando ? "0 12px 32px rgba(0,0,0,.35)" : undefined,
                outline: redimensionando
                  ? "2px solid var(--accent)"
                  : editando
                  ? "1px dashed var(--border-accent)"
                  : undefined,
              }}
            >
              {redimensionando && (
                <div
                  style={{
                    position: "absolute",
                    top: 6,
                    right: 6,
                    background: "var(--accent)",
                    color: "#ffffff",
                    fontSize: 11,
                    fontWeight: 600,
                    padding: "2px 6px",
                    borderRadius: 4,
                    pointerEvents: "none",
                    zIndex: 20,
                  }}
                >
                  {`${c.largura}/${COLUNAS_GRADE} col × ${c.altura} lin`}
                </div>
              )}

              {podeEditarGrade &&
                ALCAS.map((a) => (
                  <div
                    key={a.eixo}
                    className="dash-resize-handle"
                    title={a.titulo}
                    style={{
                      position: "absolute",
                      cursor: a.cursor,
                      zIndex: 5,
                      touchAction: "none",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      ...a.estilo,
                    }}
                    onPointerDown={(e) => {
                      if (e.button !== 0) return;
                      e.preventDefault();
                      e.stopPropagation();
                      iniciarGesto(e, w, "redimensionar", a.eixo);
                    }}
                    onDoubleClick={(e) => {
                      e.stopPropagation();
                      if (a.eixo.includes("s") || a.eixo.includes("n")) onAjustar?.(w.id);
                    }}
                  >
                    {a.eixo === "se" && (
                      <svg width="12" height="12" viewBox="0 0 12 12" style={{ pointerEvents: "none", flexShrink: 0 }}>
                        <line x1="10" y1="2" x2="2" y2="10" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round" />
                        <line x1="10" y1="5" x2="5" y2="10" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round" />
                        <line x1="10" y1="8" x2="8" y2="10" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round" />
                      </svg>
                    )}
                  </div>
                ))}

              <WidgetFrame
                widget={w}
                dados={dados?.widgets?.[w.id]}
                acoes={renderAcoes?.(w)}
                arrastavel={podeEditarGrade}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
