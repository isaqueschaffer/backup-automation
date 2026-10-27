import { ALTURA_LINHA_PX, GAP_GRADE_PX } from "./types";

// Número de linhas da grade que o conteúdo do widget realmente precisa (altura natural, sem esticar até 100%)
export function linhasDoConteudo(item: HTMLElement): number | null {
  const corpo = item.querySelector<HTMLElement>("[data-widget-corpo]");
  const conteudo = corpo?.querySelector<HTMLElement>(":scope > [data-widget-conteudo]");
  if (!corpo || !conteudo) return null;

  const alturaAnterior = conteudo.style.height;
  conteudo.style.height = "auto";
  const natural = conteudo.scrollHeight;
  conteudo.style.height = alturaAnterior;

  const moldura = item.clientHeight - corpo.clientHeight;
  const precisa = natural + moldura;
  return Math.max(1, Math.ceil((precisa + GAP_GRADE_PX) / (ALTURA_LINHA_PX + GAP_GRADE_PX)));
}
