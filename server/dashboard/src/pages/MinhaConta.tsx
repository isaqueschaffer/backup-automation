import { useState, useEffect, useCallback, FormEvent } from "react";
import { useAuth } from "../contexts/AuthContext";
import { fetchMinhaConta, trocarSenha } from "../api/contas";
import { ContaDetalhe } from "../api/types";
import { useToast } from "../components/Toast";
import { apiErrorMessage } from "../utils/errors";
import { StatusContaBadge, TIPO_CONTA_LABEL, textoValidade } from "./Contas/contaUi";
import UsuariosSection from "./Contas/UsuariosSection";
import HistoricoValidade from "./Contas/HistoricoValidade";

export default function MinhaConta() {
  const { me, recarregarMe } = useAuth();
  const { toast } = useToast();

  const [conta, setConta] = useState<ContaDetalhe | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Formulário de troca de senha
  const [senhaAtual, setSenhaAtual] = useState("");
  const [novaSenha, setNovaSenha] = useState("");
  const [confirmarNovaSenha, setConfirmarNovaSenha] = useState("");
  const [trocandoSenha, setTrocandoSenha] = useState(false);

  const temConta = !!me?.conta;
  const podeVerUsuarios =
    me?.usuario.papel === "ADMIN" || me?.usuario.papel === "SUPER_ADMIN";
  const temUsuarioId = !!me?.usuario.id;

  const loadConta = useCallback(async () => {
    if (!temConta) {
      setConta(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchMinhaConta();
      setConta(data);
    } catch (err) {
      setError(apiErrorMessage(err, "Erro ao carregar dados da conta."));
    } finally {
      setLoading(false);
    }
  }, [temConta]);

  useEffect(() => {
    loadConta();
  }, [loadConta]);

  const handleTrocarSenha = async (e: FormEvent) => {
    e.preventDefault();

    if (!senhaAtual) {
      toast("Informe a senha atual.", "error");
      return;
    }

    if (novaSenha.length < 10) {
      toast("A nova senha deve ter no mínimo 10 caracteres.", "error");
      return;
    }

    if (novaSenha !== confirmarNovaSenha) {
      toast("A nova senha e a confirmação não conferem.", "error");
      return;
    }

    setTrocandoSenha(true);
    try {
      const r = await trocarSenha(senhaAtual, novaSenha);
      try {
        localStorage.setItem("trilan_token", r.access_token);
      } catch {
        // ignora se localStorage não disponível
      }
      void recarregarMe();
      toast("Senha alterada.", "success");
      setSenhaAtual("");
      setNovaSenha("");
      setConfirmarNovaSenha("");
    } catch (err) {
      toast(apiErrorMessage(err, "Erro ao alterar a senha."), "error");
    } finally {
      setTrocandoSenha(false);
    }
  };

  const renderCardSenha = () => {
    if (!temUsuarioId) return null;
    return (
      <div className="card" style={{ marginTop: 24, maxWidth: 480 }}>
        <h3
          style={{
            fontSize: 16,
            fontWeight: 600,
            color: "var(--text-primary)",
            margin: "0 0 16px 0",
          }}
        >
          Minha senha
        </h3>
        <form onSubmit={handleTrocarSenha}>
          <div className="form-group">
            <label className="form-label">Senha atual</label>
            <input
              type="password"
              className="form-input"
              value={senhaAtual}
              onChange={(e) => setSenhaAtual(e.target.value)}
              required
              disabled={trocandoSenha}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Nova senha</label>
            <input
              type="password"
              className="form-input"
              value={novaSenha}
              onChange={(e) => setNovaSenha(e.target.value)}
              placeholder="Mínimo de 10 caracteres"
              required
              minLength={10}
              disabled={trocandoSenha}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Confirmar nova senha</label>
            <input
              type="password"
              className="form-input"
              value={confirmarNovaSenha}
              onChange={(e) => setConfirmarNovaSenha(e.target.value)}
              placeholder="Repita a nova senha"
              required
              minLength={10}
              disabled={trocandoSenha}
            />
          </div>

          <div style={{ marginTop: 20 }}>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={trocandoSenha}
            >
              {trocandoSenha ? (
                <>
                  <span className="spinner spinner-sm" /> Alterando...
                </>
              ) : (
                "Alterar senha"
              )}
            </button>
          </div>
        </form>
      </div>
    );
  };

  // 1. Super admin sem conta escolhida
  if (!temConta) {
    return (
      <>
        <div className="page-header">
          <div>
            <h1 className="page-title">Minha conta</h1>
          </div>
        </div>

        <div className="empty-state">
          <div>Escolha uma conta no menu lateral para ver os dados dela.</div>
        </div>

        {renderCardSenha()}
      </>
    );
  }

  // 2. Carregando dados da conta
  if (loading && !conta) {
    return (
      <div className="loading-state">
        <div className="spinner" />
      </div>
    );
  }

  // 3. Erro ao carregar dados da conta
  if (error && !conta) {
    return (
      <>
        <div className="page-header">
          <div>
            <h1 className="page-title">Minha conta</h1>
          </div>
        </div>

        <div className="empty-state">
          <div>{error}</div>
          <button
            type="button"
            className="btn btn-secondary mt-2"
            onClick={loadConta}
          >
            Tentar novamente
          </button>
        </div>

        {renderCardSenha()}
      </>
    );
  }

  if (!conta) return null;

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Minha conta</h1>
          <p className="page-subtitle">{conta.nome}</p>
        </div>
      </div>

      {/* Card Plano e Validade */}
      <div className="card" style={{ marginBottom: 24, maxWidth: 540 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: 12,
            marginBottom: 16,
          }}
        >
          <h3
            style={{
              fontSize: 16,
              fontWeight: 600,
              color: "var(--text-primary)",
              margin: 0,
            }}
          >
            Plano e validade
          </h3>
          <StatusContaBadge status={conta.status} />
        </div>

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 14,
            marginBottom: 20,
          }}
        >
          <div>
            <div className="text-xs text-muted">Nome da conta</div>
            <div
              style={{
                fontSize: 15,
                fontWeight: 600,
                color: "var(--text-primary)",
              }}
            >
              {conta.nome}
            </div>
          </div>

          <div>
            <div className="text-xs text-muted">Tipo de conta</div>
            <div className="text-secondary" style={{ fontSize: 14 }}>
              {TIPO_CONTA_LABEL[conta.tipo] ?? conta.tipo}
            </div>
          </div>

          <div>
            <div className="text-xs text-muted">Plano atual</div>
            <div
              style={{
                fontSize: 15,
                fontWeight: 600,
                color: "var(--text-primary)",
              }}
            >
              {conta.plano_nome ?? "—"}
            </div>
          </div>

          <div>
            <div className="text-xs text-muted">Validade</div>
            <div
              style={{
                fontSize: 15,
                fontWeight: 600,
                color: "var(--text-primary)",
              }}
            >
              {textoValidade(conta)}
            </div>
          </div>
        </div>

        <div
          className="text-muted"
          style={{
            fontSize: 13,
            padding: "10px 14px",
            background: "var(--surface-2)",
            borderRadius: "var(--radius, 8px)",
            border: "1px solid var(--border)",
          }}
        >
          Para renovar ou mudar de plano, fale com a Trilan.
        </div>
      </div>

      {/* Seção de Usuários da Conta */}
      {podeVerUsuarios && (
        <div style={{ marginBottom: 24 }}>
          <UsuariosSection podeEditar={!me?.somente_leitura} />
        </div>
      )}

      {/* Histórico de Validade */}
      <div style={{ marginBottom: 24 }}>
        <HistoricoValidade renovacoes={conta.renovacoes} />
      </div>

      {/* Card Minha Senha */}
      {renderCardSenha()}
    </>
  );
}
