import { useState, useEffect, type CSSProperties } from "react";
import { useAuth } from "../contexts/AuthContext";
import { fmtDay } from "../utils/date";
import { Building2, AlertTriangle, Lock, Eye, X } from "lucide-react";

const faixaBaseStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  padding: "10px 16px",
  borderRadius: "var(--radius-md)",
  marginBottom: 16,
  fontSize: 13.5,
};

export default function AvisoConta() {
  const { me, escolherConta } = useAuth();

  const chaveAviso =
    me?.conta?.id && me.conta.expira_em
      ? `trilan_aviso_${me.conta.id}_${me.conta.expira_em}`
      : "";

  const [avisoFechado, setAvisoFechado] = useState<boolean>(() => {
    if (!chaveAviso) return false;
    try {
      return sessionStorage.getItem(chaveAviso) === "1";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    if (!chaveAviso) {
      setAvisoFechado(false);
      return;
    }
    try {
      setAvisoFechado(sessionStorage.getItem(chaveAviso) === "1");
    } catch {
      setAvisoFechado(false);
    }
  }, [chaveAviso]);

  if (!me) return null;

  const isSuperAdmin = me.usuario.papel === "SUPER_ADMIN";
  const conta = me.conta;
  const sujeito = isSuperAdmin ? "Esta conta" : "Sua conta";
  const sujeitoMin = isSuperAdmin ? "esta conta" : "sua conta";
  const d = conta?.dias_restantes ?? 0;
  const data = fmtDay(conta?.expira_em);

  const fecharAviso = () => {
    if (chaveAviso) {
      try {
        sessionStorage.setItem(chaveAviso, "1");
      } catch {
        // sessionStorage indisponível
      }
    }
    setAvisoFechado(true);
  };

  const renderFaixaStatus = () => {
    if (!conta) return null;

    if (conta.status === "AVISO") {
      if (avisoFechado) return null;
      return (
        <div
          role="status"
          style={{
            ...faixaBaseStyle,
            background: "var(--warn-bg)",
            border: "1px solid var(--warn)",
            color: "var(--warn)",
          }}
        >
          <AlertTriangle size={18} style={{ flexShrink: 0 }} />
          <span style={{ flex: 1 }}>
            {sujeito} vence em {d === 1 ? "1 dia" : `${d} dias`} ({data}). Fale com a Trilan para renovar o plano.
          </span>
          <button
            type="button"
            aria-label="Fechar aviso"
            onClick={fecharAviso}
            style={{
              background: "transparent",
              border: "none",
              color: "inherit",
              cursor: "pointer",
              padding: 4,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              borderRadius: "var(--radius-sm)",
              opacity: 0.8,
              flexShrink: 0,
            }}
          >
            <X size={16} style={{ flexShrink: 0 }} />
          </button>
        </div>
      );
    }

    if (conta.status === "CRITICO") {
      return (
        <div
          role="status"
          style={{
            ...faixaBaseStyle,
            background: "var(--err-bg)",
            border: "1px solid var(--err)",
            color: "var(--err)",
          }}
        >
          <AlertTriangle size={18} style={{ flexShrink: 0 }} />
          <span style={{ flex: 1 }}>
            Atenção: {sujeitoMin} vence em {d === 1 ? "1 dia" : `${d} dias`} ({data}). Depois disso o painel fica somente leitura e os backups automáticos param. Fale com a Trilan para renovar.
          </span>
        </div>
      );
    }

    if (conta.status === "VENCIDA") {
      return (
        <div
          role="status"
          style={{
            ...faixaBaseStyle,
            background: "var(--err-bg)",
            border: "1px solid var(--err)",
            color: "var(--err)",
          }}
        >
          <Lock size={18} style={{ flexShrink: 0 }} />
          <span style={{ flex: 1 }}>
            {sujeito} venceu em {data}. O painel está em modo somente leitura e os backups automáticos estão suspensos. Nenhum dado foi apagado. Fale com a Trilan para renovar.
          </span>
        </div>
      );
    }

    if (conta.status === "SUSPENSA") {
      return (
        <div
          role="status"
          style={{
            ...faixaBaseStyle,
            background: "var(--err-bg)",
            border: "1px solid var(--err)",
            color: "var(--err)",
          }}
        >
          <Lock size={18} style={{ flexShrink: 0 }} />
          <span style={{ flex: 1 }}>
            {sujeito} está suspensa. O painel está em modo somente leitura e os backups automáticos estão suspensos. Fale com a Trilan.
          </span>
        </div>
      );
    }

    return null;
  };

  const mostrarSuperAdminFaixa = isSuperAdmin && !!conta;
  const mostrarLeituraFaixa =
    me.usuario.papel === "LEITURA" && (!conta || !conta.bloqueada);

  return (
    <>
      {mostrarSuperAdminFaixa && (
        <div
          role="status"
          style={{
            ...faixaBaseStyle,
            background: "var(--accent-glow)",
            border: "1px solid var(--border-accent)",
            color: "var(--text-primary)",
          }}
        >
          <Building2 size={18} style={{ flexShrink: 0 }} />
          <span style={{ flex: 1 }}>
            Visualizando a conta <strong>{conta.nome}</strong> (
            {conta.tipo === "CLIENTE_FINAL" ? "Cliente final" : "Integrador"})
          </span>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            style={{ flexShrink: 0 }}
            onClick={() => escolherConta(null)}
          >
            Ver todas as contas
          </button>
        </div>
      )}

      {renderFaixaStatus()}

      {mostrarLeituraFaixa && (
        <div
          role="status"
          style={{
            ...faixaBaseStyle,
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            color: "var(--text-secondary)",
          }}
        >
          <Eye size={18} style={{ flexShrink: 0 }} />
          <span style={{ flex: 1 }}>Seu acesso é somente leitura.</span>
        </div>
      )}
    </>
  );
}
