import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";

declare const __BUILD_ID__: string;

const VERIFICAR_A_CADA_MS = 2 * 60 * 1000;
// Recarrega sozinho quando ninguém mexe no painel há este tempo (tela de monitoramento) ou com a aba escondida;
// quem está usando vê a faixa e escolhe a hora. O login fica salvo, então a tela volta logada.
const OCIOSO_MS = 3 * 60 * 1000;

async function buildPublicado(): Promise<string | null> {
  try {
    const r = await fetch(`/version.json?t=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) return null;
    const j = await r.json(); // servidor sem o arquivo devolve o index.html: falha aqui e é ignorado
    return typeof j?.build === "string" ? j.build : null;
  } catch {
    return null;
  }
}

export default function NovaVersao() {
  const [disponivel, setDisponivel] = useState(false);

  // Procura versão nova
  useEffect(() => {
    if (import.meta.env.DEV || disponivel) return;
    // Verifica também com a aba escondida: é quando dá para recarregar sem atrapalhar ninguém
    const verificar = () => {
      void buildPublicado().then((b) => {
        if (b && b !== __BUILD_ID__) setDisponivel(true);
      });
    };
    const t = window.setInterval(verificar, VERIFICAR_A_CADA_MS);
    const aoVoltar = () => {
      if (!document.hidden) verificar();
    };
    document.addEventListener("visibilitychange", aoVoltar);
    return () => {
      window.clearInterval(t);
      document.removeEventListener("visibilitychange", aoVoltar);
    };
  }, [disponivel]);

  // Com versão nova: recarrega quando a aba estiver escondida ou o painel ficar ocioso
  useEffect(() => {
    if (!disponivel) return;
    let ultimoUso = Date.now();
    const usou = () => {
      ultimoUso = Date.now();
    };
    const eventos = ["pointerdown", "pointermove", "keydown", "wheel", "touchstart"] as const;
    eventos.forEach((e) => window.addEventListener(e, usou, { passive: true }));
    const tentar = () => {
      if (document.hidden || Date.now() - ultimoUso >= OCIOSO_MS) window.location.reload();
    };
    const t = window.setInterval(tentar, 15 * 1000);
    document.addEventListener("visibilitychange", tentar);
    return () => {
      eventos.forEach((e) => window.removeEventListener(e, usou));
      window.clearInterval(t);
      document.removeEventListener("visibilitychange", tentar);
    };
  }, [disponivel]);

  if (!disponivel) return null;

  return (
    <div className="faixa-flutuante" role="status">
      <RefreshCw size={16} style={{ flexShrink: 0 }} />
      <span>Nova versão do painel disponível.</span>
      <button type="button" className="btn btn-primary btn-sm" onClick={() => window.location.reload()}>
        Atualizar agora
      </button>
    </div>
  );
}
