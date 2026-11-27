import { ALTURA_MAX_GRADE, COLUNAS_GRADE, WidgetInstancia } from "./types";

// Motor da grade livre do Dashboard por Cliente: posição (x, y) em colunas/linhas, sem
// sobreposição e com empilhamento para cima (sem buracos). O backend aplica a mesma regra
// em services/dashboards/layout.py ao salvar.

export interface Caixa {
  x: number;
  y: number;
  largura: number;
  altura: number;
}

export function colide(a: Caixa, b: Caixa): boolean {
  return (
    a.x < b.x + b.largura &&
    b.x < a.x + a.largura &&
    a.y < b.y + b.altura &&
    b.y < a.y + a.altura
  );
}

export function ordenarPorPosicao<T extends Caixa>(itens: T[]): T[] {
  return [...itens].sort((a, b) => a.y - b.y || a.x - b.x);
}

export function fundoDaGrade(itens: Caixa[]): number {
  return itens.reduce((m, w) => Math.max(m, w.y + w.altura), 0);
}

export function limitarCaixa(c: Caixa, larguraMin = 1, alturaMin = 1): Caixa {
  const largura = Math.max(larguraMin, Math.min(COLUNAS_GRADE, Math.round(c.largura)));
  const altura = Math.max(alturaMin, Math.min(ALTURA_MAX_GRADE, Math.round(c.altura)));
  return {
    largura,
    altura,
    x: Math.max(0, Math.min(COLUNAS_GRADE - largura, Math.round(c.x))),
    y: Math.max(0, Math.round(c.y)),
  };
}

// Sobe cada widget até encostar no de cima e desfaz sobreposições (de cima para baixo)
export function compactar(widgets: WidgetInstancia[]): WidgetInstancia[] {
  const colocados: WidgetInstancia[] = [];
  for (const original of ordenarPorPosicao(widgets)) {
    const w = { ...original };
    w.y = colocados.reduce(
      (m, o) =>
        o.x < w.x + w.largura && w.x < o.x + o.largura && o.y + o.altura <= w.y
          ? Math.max(m, o.y + o.altura)
          : m,
      0
    );
    let choque = colocados.find((o) => colide(w, o));
    while (choque) {
      w.y = choque.y + choque.altura;
      choque = colocados.find((o) => colide(w, o));
    }
    colocados.push(w);
  }
  return colocados;
}

// Coloca um widget numa caixa e tira do caminho quem estiver lá; depois compacta.
// `base` é o layout do início do gesto (as prévias são sempre calculadas a partir dele).
export function posicionar(base: WidgetInstancia[], id: string, caixa: Caixa): WidgetInstancia[] {
  const alvo = base.find((w) => w.id === id);
  if (!alvo) return base;
  const movido: WidgetInstancia = { ...alvo, ...limitarCaixa(caixa) };
  const desceu = movido.y > alvo.y;
  const colocados: WidgetInstancia[] = [movido];

  for (const original of ordenarPorPosicao(base.filter((w) => w.id !== id))) {
    const w = { ...original };
    // Ao arrastar para baixo por cima de um widget, ele troca de lugar e sobe para cima do movido
    if (desceu && colide(w, movido)) {
      const acima = movido.y - w.altura;
      if (acima >= 0 && !colocados.some((o) => colide({ ...w, y: acima }, o))) {
        w.y = acima;
      }
    }
    let choque = colocados.find((o) => colide(w, o));
    while (choque) {
      w.y = choque.y + choque.altura;
      choque = colocados.find((o) => colide(w, o));
    }
    colocados.push(w);
  }
  return compactar(colocados);
}

// Primeiro lugar livre, de cima para baixo e da esquerda para a direita
export function primeiroLugarLivre(
  widgets: Caixa[],
  largura: number,
  altura: number
): { x: number; y: number } {
  const fundo = fundoDaGrade(widgets);
  for (let y = 0; y <= fundo; y++) {
    for (let x = 0; x <= COLUNAS_GRADE - largura; x++) {
      if (!widgets.some((o) => colide({ x, y, largura, altura }, o))) {
        return { x, y };
      }
    }
  }
  return { x: 0, y: fundo };
}

export function mesmasPosicoes(a: WidgetInstancia[], b: WidgetInstancia[]): boolean {
  if (a.length !== b.length) return false;
  const porId = new Map(b.map((w) => [w.id, w]));
  return a.every((w) => {
    const o = porId.get(w.id);
    return (
      !!o && o.x === w.x && o.y === w.y && o.largura === w.largura && o.altura === w.altura
    );
  });
}
