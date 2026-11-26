import { useSyncExternalStore } from "react";

// Estado da conexão com a API, alimentado pelo interceptor do axios (api/client.ts):
// falha de rede ou 502/503/504 = sem conexão; qualquer resposta do servidor = conectado.
let conectado = true;
const ouvintes = new Set<() => void>();

export function marcarConexao(ok: boolean) {
  if (ok === conectado) return;
  conectado = ok;
  ouvintes.forEach((fn) => fn());
}

function assinar(fn: () => void) {
  ouvintes.add(fn);
  return () => {
    ouvintes.delete(fn);
  };
}

export const useConectado = () => useSyncExternalStore(assinar, () => conectado);
