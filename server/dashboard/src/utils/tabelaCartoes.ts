// Tabelas com a classe "tabela-cartoes" viram cartões empilhados no celular (CSS em index.css).
// Cada célula ganha data-label com o título da coluna, lido do <thead>, para o CSS mostrar
// "Coluna: valor" sem precisar rotular célula por célula nos componentes.
function rotular(tabela: HTMLTableElement) {
  const titulos = Array.from(tabela.tHead?.rows[0]?.cells ?? []).map((th) => th.textContent?.trim() ?? "");
  for (const corpo of Array.from(tabela.tBodies)) {
    for (const linha of Array.from(corpo.rows)) {
      let col = 0;
      for (const celula of Array.from(linha.cells)) {
        const rotulo = celula.colSpan > 1 ? "" : titulos[col] ?? "";
        if (celula.getAttribute("data-label") !== rotulo) celula.setAttribute("data-label", rotulo);
        col += celula.colSpan;
      }
    }
  }
}

/** Observa a página e mantém os rótulos das tabelas-cartão em dia. Devolve a função de parar. */
export function observarTabelasCartoes(raiz: HTMLElement): () => void {
  let agendado = 0;
  const aplicar = () => {
    agendado = 0;
    raiz.querySelectorAll<HTMLTableElement>("table.tabela-cartoes").forEach(rotular);
  };
  aplicar();
  const obs = new MutationObserver(() => {
    if (!agendado) agendado = requestAnimationFrame(aplicar);
  });
  obs.observe(raiz, { childList: true, subtree: true, characterData: true });
  return () => {
    obs.disconnect();
    if (agendado) cancelAnimationFrame(agendado);
  };
}
