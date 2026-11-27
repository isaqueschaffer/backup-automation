import type { KeyboardEvent } from "react";

// Área clicável que não é <button>/<a> (card, cabeçalho de linha expansível): ganha foco pelo Tab e responde a
// Enter (e Espaço, quando é botão), para quem usa teclado ou leitor de tela. Prefira <button> quando der.
export function propsClicavel(acao: () => void, papel: "button" | "link" = "button") {
  return {
    role: papel,
    tabIndex: 0,
    onClick: acao,
    onKeyDown: (e: KeyboardEvent<HTMLElement>) => {
      if (e.target !== e.currentTarget) return; // tecla num botão de dentro: ele mesmo trata
      if (e.key === "Enter" || (papel === "button" && e.key === " ")) {
        e.preventDefault();
        acao();
      }
    },
  };
}
