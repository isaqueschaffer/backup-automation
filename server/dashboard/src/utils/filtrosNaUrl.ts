import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";

// Filtros das listas no endereço da página (?cliente=...&status=...): o link pode ser enviado a alguém, recarregar
// não perde o filtro e voltar de uma tela de detalhe devolve a lista como estava.
// Uso: o estado continua local (useState iniciado com lerFiltro) e useFiltrosNaUrl grava na URL quando ele muda.
// Assim dois filtros mudados no mesmo clique (cliente e máquina) não se atropelam.

export function lerFiltro(params: URLSearchParams, chave: string, padrao = ""): string {
  return params.get(chave) ?? padrao;
}

// `filtros`: chave na URL -> valor atual. Valor vazio ou igual ao padrão sai da URL.
export function useFiltrosNaUrl(filtros: Record<string, string>, padroes: Record<string, string> = {}) {
  const [params, setParams] = useSearchParams();
  const assinatura = JSON.stringify(filtros) + JSON.stringify(padroes);

  useEffect(() => {
    const prox = new URLSearchParams(params);
    for (const [chave, valor] of Object.entries(filtros)) {
      if (valor && valor !== (padroes[chave] ?? "")) prox.set(chave, valor);
      else prox.delete(chave);
    }
    if (prox.toString() === params.toString()) return;
    setParams(prox, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assinatura]);
}
