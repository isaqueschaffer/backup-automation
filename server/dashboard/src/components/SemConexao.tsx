import { useEffect } from "react";
import { WifiOff } from "lucide-react";
import { fetchMe } from "../api/contas";
import { useConectado } from "../utils/conexao";

// Aviso de "sem conexão com o servidor": a tela continua com os últimos dados e tenta de novo sozinha.
// Enquanto estiver sem conexão, testa a cada 15 s (a resposta do servidor apaga o aviso pelo interceptor).
export default function SemConexao() {
  const conectado = useConectado();

  useEffect(() => {
    if (conectado) return;
    const t = window.setInterval(() => {
      fetchMe().catch(() => { /* continua tentando */ });
    }, 15 * 1000);
    return () => window.clearInterval(t);
  }, [conectado]);

  if (conectado) return null;

  return (
    <div className="faixa-flutuante faixa-flutuante-erro" role="alert">
      <WifiOff size={16} style={{ flexShrink: 0 }} />
      <span>Sem conexão com o servidor. Mostrando os últimos dados; tentando de novo…</span>
    </div>
  );
}
