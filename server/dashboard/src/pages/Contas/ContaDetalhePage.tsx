import { useCallback, useEffect, useMemo, useState, FormEvent } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, LogIn, Edit2, RefreshCw } from "lucide-react";
import {
  fetchConta,
  fetchPlanos,
  updateConta,
  renovarConta,
  suspenderConta,
  reativarConta,
  NovaContaPayload,
  EditarContaPayload,
} from "../../api/contas";
import { ContaDetalhe, Plano } from "../../api/types";
import Modal from "../../components/Modal";
import { useToast } from "../../components/Toast";
import { useAuth } from "../../contexts/AuthContext";
import { fmtDay } from "../../utils/date";
import { apiErrorMessage } from "../../utils/errors";
import { StatusContaBadge, TIPO_CONTA_LABEL, textoValidade } from "./contaUi";
import ContaFormModal from "./ContaFormModal";
import UsuariosSection from "./UsuariosSection";
import HistoricoValidade from "./HistoricoValidade";

export default function ContaDetalhePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { escolherConta } = useAuth();

  const [conta, setConta] = useState<ContaDetalhe | null>(null);
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal Editar Conta
  const [showEditModal, setShowEditModal] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);

  // Modal Renovar
  const [showRenovarModal, setShowRenovarModal] = useState(false);
  const [planoRenovarId, setPlanoRenovarId] = useState("");
  const [renovando, setRenovando] = useState(false);

  // Suspender / Reativar
  const [alterandoStatus, setAlterandoStatus] = useState(false);

  const loadDados = useCallback(async () => {
    if (!id) return;
    try {
      setError(null);
      const [contaData, planosData] = await Promise.all([
        fetchConta(id),
        fetchPlanos(),
      ]);
      setConta(contaData);
      setPlanos(planosData);
    } catch (err) {
      setError(apiErrorMessage(err, "Conta não encontrada."));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    setLoading(true);
    loadDados();
  }, [loadDados]);

  const planosAtivos = useMemo(() => planos.filter((p) => p.ativo), [planos]);

  // Atualiza plano selecionado padrão para renovação
  useEffect(() => {
    if (showRenovarModal && !planoRenovarId && planosAtivos.length > 0) {
      setPlanoRenovarId(planosAtivos[0].id);
    }
  }, [showRenovarModal, planoRenovarId, planosAtivos]);

  const planoEscolhido = planosAtivos.find((p) => p.id === planoRenovarId);

  const previaValidadeStr = useMemo(() => {
    if (!planoEscolhido || !conta) return null;
    let base = new Date();
    if (conta.expira_em) {
      const expStr = conta.expira_em.endsWith("Z") ? conta.expira_em : `${conta.expira_em}Z`;
      const expDate = new Date(expStr);
      if (expDate > new Date()) {
        base = expDate;
      }
    }
    const novaValidade = new Date(base);
    novaValidade.setDate(novaValidade.getDate() + planoEscolhido.duracao_dias);
    return fmtDay(novaValidade.toISOString());
  }, [planoEscolhido, conta]);

  const handleUpdateConta = async (
    dados: NovaContaPayload | Partial<EditarContaPayload>
  ) => {
    if (!id) return;
    setSavingEdit(true);
    try {
      await updateConta(id, dados as Partial<EditarContaPayload>);
      toast("Conta atualizada com sucesso.", "success");
      setShowEditModal(false);
      await loadDados();
    } catch (err) {
      toast(apiErrorMessage(err, "Erro ao atualizar conta."), "error");
    } finally {
      setSavingEdit(false);
    }
  };

  const handleRenovar = async (e: FormEvent) => {
    e.preventDefault();
    if (!id || !planoRenovarId) {
      toast("Selecione um plano para renovar.", "error");
      return;
    }
    setRenovando(true);
    try {
      const atualizada = await renovarConta(id, planoRenovarId);
      toast(`Conta renovada até ${fmtDay(atualizada.expira_em)}.`, "success");
      setShowRenovarModal(false);
      await loadDados();
    } catch (err) {
      toast(apiErrorMessage(err, "Erro ao renovar conta."), "error");
    } finally {
      setRenovando(false);
    }
  };

  const handleSuspender = async () => {
    if (!id) return;
    if (
      !confirm(
        "Suspender a conta? O painel dela fica somente leitura e os backups param até reativar."
      )
    ) {
      return;
    }

    setAlterandoStatus(true);
    try {
      await suspenderConta(id);
      toast("Conta suspensa.", "success");
      await loadDados();
    } catch (err) {
      toast(apiErrorMessage(err, "Erro ao suspender conta."), "error");
    } finally {
      setAlterandoStatus(false);
    }
  };

  const handleReativar = async () => {
    if (!id) return;
    setAlterandoStatus(true);
    try {
      await reativarConta(id);
      toast("Conta reativada.", "success");
      await loadDados();
    } catch (err) {
      toast(apiErrorMessage(err, "Erro ao reativar conta."), "error");
    } finally {
      setAlterandoStatus(false);
    }
  };

  if (loading) {
    return (
      <div className="loading-state">
        <div className="spinner" />
      </div>
    );
  }

  if (error || !conta) {
    return (
      <div className="empty-state">
        <div>{error ?? "Conta não encontrada."}</div>
        <button
          type="button"
          className="btn btn-primary mt-3"
          onClick={() => navigate("/contas")}
        >
          Voltar para Contas
        </button>
      </div>
    );
  }

  return (
    <>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            type="button"
            className="btn-icon"
            onClick={() => navigate("/contas")}
            title="Voltar para Contas"
          >
            <ArrowLeft size={18} style={{ flexShrink: 0 }} />
          </button>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <h1 className="page-title" style={{ margin: 0 }}>
                {conta.nome}
              </h1>
              <StatusContaBadge status={conta.status} />
              <span className="badge muted">
                {TIPO_CONTA_LABEL[conta.tipo] ?? conta.tipo}
              </span>
              {conta.plataforma && (
                <span className="badge muted">Plataforma</span>
              )}
            </div>
            {conta.documento && (
              <p className="page-subtitle" style={{ margin: "4px 0 0 0" }}>
                {conta.documento}
              </p>
            )}
          </div>
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => escolherConta(conta.id)}
          >
            <LogIn size={15} style={{ flexShrink: 0 }} /> Entrar na conta
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setShowEditModal(true)}
          >
            <Edit2 size={15} style={{ flexShrink: 0 }} /> Editar
          </button>
        </div>
      </div>

      {/* Grid com Plano/Validade e Dados da Conta */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: 20,
          marginBottom: 24,
        }}
      >
        {/* Card Plano e Validade */}
        <div className="card">
          <h3
            style={{
              fontSize: 16,
              fontWeight: 600,
              color: "var(--text-primary)",
              margin: "0 0 16px 0",
            }}
          >
            Plano e validade
          </h3>

          {conta.plataforma ? (
            <div className="text-secondary" style={{ fontSize: 14 }}>
              Conta da plataforma: sem validade.
            </div>
          ) : (
            <>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 12,
                  marginBottom: 20,
                }}
              >
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

                <div>
                  <div className="text-xs text-muted">Criada em</div>
                  <div className="text-secondary" style={{ fontSize: 14 }}>
                    {fmtDay(conta.criado_em)}
                  </div>
                </div>
              </div>

              <div className="flex gap-2" style={{ flexWrap: "wrap" }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => setShowRenovarModal(true)}
                >
                  <RefreshCw size={15} style={{ flexShrink: 0 }} /> Renovar
                </button>

                {conta.status === "SUSPENSA" ? (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={alterandoStatus}
                    onClick={handleReativar}
                  >
                    Reativar
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn btn-danger"
                    disabled={alterandoStatus}
                    onClick={handleSuspender}
                  >
                    Suspender
                  </button>
                )}
              </div>
            </>
          )}
        </div>

        {/* Card Dados da Conta */}
        <div className="card">
          <h3
            style={{
              fontSize: 16,
              fontWeight: 600,
              color: "var(--text-primary)",
              margin: "0 0 16px 0",
            }}
          >
            Dados da conta
          </h3>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 12,
              marginBottom: 16,
            }}
          >
            <div>
              <div className="text-xs text-muted">Tipo</div>
              <div style={{ fontSize: 14, color: "var(--text-primary)" }}>
                {TIPO_CONTA_LABEL[conta.tipo] ?? conta.tipo}
              </div>
            </div>

            <div>
              <div className="text-xs text-muted">CPF / CNPJ</div>
              <div style={{ fontSize: 14, color: "var(--text-primary)" }}>
                {conta.documento ?? "—"}
              </div>
            </div>

            <div>
              <div className="text-xs text-muted">E-mail de contato</div>
              <div style={{ fontSize: 14, color: "var(--text-primary)" }}>
                {conta.email_contato ?? "—"}
              </div>
            </div>

            <div>
              <div className="text-xs text-muted">Telefone</div>
              <div style={{ fontSize: 14, color: "var(--text-primary)" }}>
                {conta.telefone ?? "—"}
              </div>
            </div>
          </div>

          <div style={{ marginBottom: 16 }}>
            <div className="text-xs text-muted">Observações</div>
            <div
              style={{
                fontSize: 14,
                color: "var(--text-secondary)",
                whiteSpace: "pre-wrap",
              }}
            >
              {conta.observacoes ?? "—"}
            </div>
          </div>

          <div
            style={{
              paddingTop: 12,
              borderTop: "1px solid var(--border)",
              display: "flex",
              gap: 20,
              flexWrap: "wrap",
            }}
          >
            <div>
              <div className="text-xs text-muted">
                {conta.tipo === "CLIENTE_FINAL" ? "Setores" : "Clientes"}
              </div>
              <div
                style={{
                  fontSize: 16,
                  fontWeight: 700,
                  color: "var(--text-primary)",
                }}
              >
                {conta.total_clientes}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted">Máquinas</div>
              <div
                style={{
                  fontSize: 16,
                  fontWeight: 700,
                  color: "var(--text-primary)",
                }}
              >
                {conta.total_maquinas}
              </div>
            </div>
            <div>
              <div className="text-xs text-muted">Usuários</div>
              <div
                style={{
                  fontSize: 16,
                  fontWeight: 700,
                  color: "var(--text-primary)",
                }}
              >
                {conta.total_usuarios}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Seção de Usuários da Conta */}
      <div style={{ marginTop: 24 }}>
        <UsuariosSection contaId={conta.id} podeEditar={true} />
      </div>

      {/* Histórico de Validade */}
      <HistoricoValidade renovacoes={conta.renovacoes} />

      {/* Modal Editar Conta */}
      {showEditModal && (
        <ContaFormModal
          modo="editar"
          conta={conta}
          planos={planos}
          saving={savingEdit}
          onSave={handleUpdateConta}
          onClose={() => setShowEditModal(false)}
        />
      )}

      {/* Modal Renovar Conta */}
      {showRenovarModal && (
        <Modal
          title="Renovar conta"
          onClose={() => {
            if (!renovando) setShowRenovarModal(false);
          }}
          width={480}
        >
          <form onSubmit={handleRenovar}>
            <div className="form-group">
              <label className="form-label">Plano de renovação *</label>
              <select
                className="form-input"
                value={planoRenovarId}
                onChange={(e) => setPlanoRenovarId(e.target.value)}
                required
              >
                {planosAtivos.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nome} — {p.duracao_dias} dias
                  </option>
                ))}
              </select>
            </div>

            {previaValidadeStr && (
              <div
                style={{
                  padding: "10px 14px",
                  background: "var(--surface-2)",
                  borderRadius: "var(--radius-sm, 6px)",
                  border: "1px solid var(--border)",
                  fontSize: 13,
                  color: "var(--text-primary)",
                  marginBottom: 16,
                }}
              >
                <strong>Nova validade prevista:</strong> {previaValidadeStr}
                <div
                  className="text-xs text-muted"
                  style={{ marginTop: 4, lineHeight: 1.35 }}
                >
                  Acrescenta {planoEscolhido?.duracao_dias} dias a partir da
                  validade atual (ou de hoje, se já vencida).
                </div>
              </div>
            )}

            <div
              className="flex gap-3 mt-4"
              style={{ justifyContent: "flex-end" }}
            >
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowRenovarModal(false)}
                disabled={renovando}
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={renovando || !planoRenovarId}
              >
                {renovando ? (
                  <span className="spinner spinner-sm" />
                ) : (
                  "Confirmar renovação"
                )}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
