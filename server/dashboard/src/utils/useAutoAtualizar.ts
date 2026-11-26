import { useEffect, useRef } from "react";

// Chama `fn` a cada `ms` enquanto a aba está visível (aba escondida não consulta o servidor à toa).
// Ao voltar a ficar visível, atualiza na hora se já passou o intervalo. Use para atualização silenciosa:
// `fn` não deve mostrar carregando nem toast de erro (tenta de novo no próximo ciclo).
export function useAutoAtualizar(fn: () => void, ms: number, ativo = true) {
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    if (!ativo) return;
    let ultima = Date.now();
    const rodar = () => {
      ultima = Date.now();
      fnRef.current();
    };
    const t = window.setInterval(() => {
      if (!document.hidden) rodar();
    }, ms);
    const aoMudarVisibilidade = () => {
      if (!document.hidden && Date.now() - ultima >= ms) rodar();
    };
    document.addEventListener("visibilitychange", aoMudarVisibilidade);
    return () => {
      window.clearInterval(t);
      document.removeEventListener("visibilitychange", aoMudarVisibilidade);
    };
  }, [ms, ativo]);
}
