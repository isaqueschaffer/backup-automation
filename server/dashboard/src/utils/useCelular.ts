import { useEffect, useState } from "react";

// Mesmo ponto de quebra do CSS (index.css): até 768px o painel usa o layout de celular.
const CELULAR = "(max-width: 768px)";

/** true quando a tela está no layout de celular; acompanha giro de tela e redimensionamento. */
export function useCelular(): boolean {
  const [celular, setCelular] = useState(
    () => typeof window !== "undefined" && window.matchMedia(CELULAR).matches
  );
  useEffect(() => {
    const m = window.matchMedia(CELULAR);
    const aoMudar = () => setCelular(m.matches);
    aoMudar();
    m.addEventListener("change", aoMudar);
    return () => m.removeEventListener("change", aoMudar);
  }, []);
  return celular;
}
