// Liga cada rótulo ao seu campo (label -> htmlFor/id) quando o componente não fez isso: o leitor de tela anuncia
// o nome do campo e clicar no rótulo foca o campo. Mesmo esquema de utils/tabelaCartoes.ts (observa a página).
// Só liga quando não há dúvida: o rótulo não aponta para nada, não envolve um campo, e o grupo dele (o elemento
// pai) tem um único rótulo e um único campo.
const CAMPOS = "input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea";
let seq = 0;

function ligar(raiz: HTMLElement) {
  raiz.querySelectorAll<HTMLLabelElement>("label:not([for])").forEach((rotulo) => {
    if (rotulo.querySelector("input, select, textarea")) return; // envolve o campo: já é associado
    const grupo = rotulo.parentElement;
    if (!grupo) return;
    const rotulos = Array.from(grupo.children).filter((el) => el.tagName === "LABEL");
    if (rotulos.length !== 1) return;
    const campos = grupo.querySelectorAll<HTMLElement>(CAMPOS);
    if (campos.length !== 1) return;
    const campo = campos[0];
    if (campo.getAttribute("aria-labelledby")) return;
    if (!campo.id) campo.id = `campo-auto-${++seq}`;
    rotulo.htmlFor = campo.id;
  });
}

/** Observa a página e liga os rótulos novos. Devolve a função de parar. */
export function observarRotulosCampos(raiz: HTMLElement): () => void {
  let agendado = 0;
  const aplicar = () => {
    agendado = 0;
    ligar(raiz);
  };
  aplicar();
  const obs = new MutationObserver(() => {
    if (!agendado) agendado = requestAnimationFrame(aplicar);
  });
  obs.observe(raiz, { childList: true, subtree: true });
  return () => {
    obs.disconnect();
    if (agendado) cancelAnimationFrame(agendado);
  };
}
