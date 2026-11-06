import { useCallback, useEffect, useMemo, useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  Building2,
  Calendar,
  LogIn,
  Plus,
  Search,
  ShieldAlert,
  SlidersHorizontal,
  UserCheck,
  UserX,
} from "lucide-react";
import {
  fetchContas,
  fetchPlanos,
  createConta,
  fetchSuperAdmins,
  createSuperAdmin,
  updateSuperAdmin,
  NovaContaPayload,
  EditarContaPayload,
} from "../../api/contas";
import { Conta, Plano, Usuario } from "../../api/types";
import Modal from "../../components/Modal";
import { useToast } from "../../components/Toast";
import { useAuth } from "../../contexts/AuthContext";
import { fmtDate } from "../../utils/date";
import { apiErrorMessage } from "../../utils/errors";
import { StatusContaBadge, TIPO_CONTA_LABEL, textoValidade } from "./contaUi";
import ContaFormModal from "./ContaFormModal";
import PlanosModal from "./PlanosModal";

function SuperAdminsSection() {
  const { toast } = useToast();
  const [superAdmins, setSuperAdmins] = useState<Usuario[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showNovo, setShowNovo] = useState(false);
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [saving, setSaving] = useState(false);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const data = await fetchSuperAdmins();
      setSuperAdmins(data);
    } catch (err) {
      setError(apiErrorMessage(err, "Erro ao carregar administradores."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleCriar = async (e: FormEvent) => {
    e.preventDefault();
    const nomeTrim = nome.trim();
    const emailTrim = email.trim();

    if (!nomeTrim || !emailTrim) {
      toast("Nome e e-mail são obrigatórios.", "error");
      return;
    }
    if (senha.length < 10) {
      toast("A senha deve ter no mínimo 10 caracteres.", "error");
      return;
    }

    setSaving(true);
    try {
      await createSuperAdmin({
        nome: nomeTrim,
        email: emailTrim,
        senha,
      });
      toast("Administrador criado com sucesso.", "success");
      setShowNovo(false);
      setNome("");
      setEmail("");
      setSenha("");
      await load();
    } catch (err) {
      toast(apiErrorMessage(err, "Erro ao criar administrador."), "error");
    } finally {
      setSaving(false);
    }
  };

  const handleToggleAtivo = async (u: Usuario) => {
    const acao = u.ativo ? "desativar" : "ativar";
    const msg = u.ativo
      ? `Desativar o administrador "${u.nome}"? Ele não conseguirá mais acessar a plataforma.`
      : `Ativar o administrador "${u.nome}"?`;

    if (!confirm(msg)) return;

    setTogglingId(u.id);
    try {
      await updateSuperAdmin(u.id, { ativo: !u.ativo });
      toast(`Administrador ${u.ativo ? "desativado" : "ativado"}.`, "success");
      await load();
    } catch (err) {
      toast(apiErrorMessage(err, `Erro ao ${acao} administrador.`), "error");
    } finally {
      setTogglingId(null);
    }
  };

  return (
    <div className="card" style={{ marginTop: 32 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 12,
          marginBottom: 16,
        }}
      >
        <div>
          <h3
            style={{
              fontSize: 16,
              fontWeight: 600,
              color: "var(--text-primary)",
              margin: "0 0 4px 0",
            }}
          >
            Administradores da plataforma
          </h3>
          <p
            className="text-xs text-muted"
            style={{ margin: 0, maxWidth: 640, lineHeight: 1.4 }}
          >
            Entram com e-mail e senha e veem todas as contas. A senha única de
            administrador (Configurações) continua valendo.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={() => {
            setNome("");
            setEmail("");
            setSenha("");
            setShowNovo(true);
          }}
        >
          <Plus size={14} style={{ flexShrink: 0 }} /> Novo administrador
        </button>
      </div>

      {loading ? (
        <div className="loading-state">
          <div className="spinner" />
        </div>
      ) : error && superAdmins.length === 0 ? (
        <div className="empty-state">
          <div>{error}</div>
          <button
            type="button"
            className="btn btn-secondary mt-2"
            onClick={() => {
              setLoading(true);
              load();
            }}
          >
            Tentar novamente
          </button>
        </div>
      ) : superAdmins.length === 0 ? (
        <div className="empty-state">
          <div>Nenhum administrador cadastrado.</div>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Nome</th>
                <th>E-mail</th>
                <th>Situação</th>
                <th>Último acesso</th>
                <th style={{ width: 80 }}>Ações</th>
              </tr>
            </thead>
            <tbody>
              {superAdmins.map((u) => (
                <tr key={u.id}>
                  <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                    {u.nome}
                  </td>
                  <td>{u.email}</td>
                  <td>
                    {u.ativo ? (
                      <span className="badge ok">Ativo</span>
                    ) : (
                      <span className="badge muted">Inativo</span>
                    )}
                  </td>
                  <td className="text-secondary text-sm">
                    {fmtDate(u.ultimo_login, { empty: "Nunca" })}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn-icon"
                      title={u.ativo ? "Desativar administrador" : "Ativar administrador"}
                      disabled={togglingId === u.id}
                      onClick={() => handleToggleAtivo(u)}
                      style={
                        u.ativo
                          ? { color: "var(--err)" }
                          : { color: "var(--ok)" }
                      }
                    >
                      {u.ativo ? (
                        <UserX size={15} style={{ flexShrink: 0 }} />
                      ) : (
                        <UserCheck size={15} style={{ flexShrink: 0 }} />
                      )}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showNovo && (
        <Modal
          title="Novo administrador da plataforma"
          onClose={() => {
            if (!saving) setShowNovo(false);
          }}
          width={480}
        >
          <form onSubmit={handleCriar}>
            <div className="form-group">
              <label className="form-label">Nome *</label>
              <input
                type="text"
                className="form-input"
                placeholder="Nome completo"
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">E-mail *</label>
              <input
                type="email"
                className="form-input"
                placeholder="admin@empresa.com.br"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Senha *</label>
              <input
                type="password"
                className="form-input"
                placeholder="Mínimo de 10 caracteres"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                required
                minLength={10}
              />
              <div className="text-xs text-muted" style={{ marginTop: 4 }}>
                Mínimo de 10 caracteres. Passe a senha ao administrador por um canal
                seguro.
              </div>
            </div>
            <div
              className="flex gap-3 mt-4"
              style={{ justifyContent: "flex-end" }}
            >
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowNovo(false)}
                disabled={saving}
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={saving}
              >
                {saving ? (
                  <span className="spinner spinner-sm" />
                ) : (
                  "Criar administrador"
                )}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

export default function ContasPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { escolherConta } = useAuth();

  const [contas, setContas] = useState<Conta[]>([]);
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Modais
  const [showPlanosModal, setShowPlanosModal] = useState(false);
  const [showNovoContaModal, setShowNovoContaModal] = useState(false);
  const [savingNovo, setSavingNovo] = useState(false);

  // Filtros
  const [busca, setBusca] = useState("");
  const [situacaoFilter, setSituacaoFilter] = useState<
    "TODAS" | "EM_DIA" | "VENCENDO" | "BLOQUEADAS"
  >("TODAS");
  const [tipoFilter, setTipoFilter] = useState<
    "TODOS" | "INTEGRADOR" | "CLIENTE_FINAL"
  >("TODOS");

  const loadDados = useCallback(async () => {
    try {
      setLoadError(null);
      const [contasData, planosData] = await Promise.all([
        fetchContas(),
        fetchPlanos(),
      ]);
      setContas(contasData);
      setPlanos(planosData);
    } catch (err) {
      setLoadError(apiErrorMessage(err, "Erro ao carregar dados de contas."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDados();
  }, [loadDados]);

  const handleCreateConta = async (
    dados: NovaContaPayload | Partial<EditarContaPayload>
  ) => {
    setSavingNovo(true);
    try {
      const nova = await createConta(dados as NovaContaPayload);
      toast("Conta criada.", "success");
      setShowNovoContaModal(false);
      navigate(`/contas/${nova.id}`);
    } catch (err) {
      toast(apiErrorMessage(err, "Erro ao criar conta."), "error");
    } finally {
      setSavingNovo(false);
    }
  };

  // Contagens para os stat-cards
  const totalContas = contas.length;

  const vencendo15Dias = useMemo(() => {
    return contas.filter((c) => {
      if (c.bloqueada || c.status === "VENCIDA" || c.status === "SUSPENSA") {
        return false;
      }
      if (c.status === "AVISO" || c.status === "CRITICO") return true;
      if (
        c.dias_restantes !== null &&
        c.dias_restantes >= 0 &&
        c.dias_restantes <= 15
      ) {
        return true;
      }
      return false;
    }).length;
  }, [contas]);

  const bloqueadasCount = useMemo(() => {
    return contas.filter(
      (c) => c.bloqueada || c.status === "VENCIDA" || c.status === "SUSPENSA"
    ).length;
  }, [contas]);

  // Filtragem e ordenação
  const contasFiltradas = useMemo(() => {
    const termo = busca.trim().toLowerCase();

    return contas
      .filter((c) => {
        // Busca textual
        if (termo) {
          const matchNome = c.nome.toLowerCase().includes(termo);
          const matchDoc = c.documento
            ? c.documento.toLowerCase().includes(termo)
            : false;
          if (!matchNome && !matchDoc) return false;
        }

        // Filtro por situação
        if (situacaoFilter === "EM_DIA") {
          if (c.status !== "OK" && c.status !== "VITALICIA") return false;
        } else if (situacaoFilter === "VENCENDO") {
          if (c.status !== "AVISO" && c.status !== "CRITICO") return false;
        } else if (situacaoFilter === "BLOQUEADAS") {
          if (!c.bloqueada && c.status !== "VENCIDA" && c.status !== "SUSPENSA") {
            return false;
          }
        }

        // Filtro por tipo
        if (tipoFilter !== "TODOS") {
          if (c.tipo !== tipoFilter) return false;
        }

        return true;
      })
      .sort((a, b) => {
        // 1. Bloqueadas primeiro
        const aBloq =
          a.bloqueada || a.status === "VENCIDA" || a.status === "SUSPENSA";
        const bBloq =
          b.bloqueada || b.status === "VENCIDA" || b.status === "SUSPENSA";
        if (aBloq && !bBloq) return -1;
        if (!aBloq && bBloq) return 1;

        // 2. Dias restantes crescente (null / vitalícia por último)
        const aDias = a.dias_restantes !== null ? a.dias_restantes : 9999999;
        const bDias = b.dias_restantes !== null ? b.dias_restantes : 9999999;
        if (aDias !== bDias) {
          return aDias - bDias;
        }

        // 3. Ordem alfabética pelo nome
        return a.nome.localeCompare(b.nome, "pt-BR");
      });
  }, [contas, busca, situacaoFilter, tipoFilter]);

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Contas</h1>
          <p className="page-subtitle">
            {loading ? "Carregando contas..." : `${contas.length} conta(s)`}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setShowPlanosModal(true)}
          >
            <SlidersHorizontal size={15} style={{ flexShrink: 0 }} /> Planos
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setShowNovoContaModal(true)}
          >
            <Plus size={15} style={{ flexShrink: 0 }} /> Nova conta
          </button>
        </div>
      </div>

      {/* Resumo de Contas */}
      <div className="stats-grid" style={{ marginBottom: 20 }}>
        <div className="stat-card cyan">
          <div className="stat-label">Total de contas</div>
          <div className="stat-value cyan">{loading ? "—" : totalContas}</div>
          <Building2
            size={28}
            className="stat-icon"
            color="var(--cyan)"
            style={{ flexShrink: 0 }}
          />
        </div>
        <div className="stat-card yellow">
          <div className="stat-label">Vencendo em até 15 dias</div>
          <div className="stat-value yellow">
            {loading ? "—" : vencendo15Dias}
          </div>
          <Calendar
            size={28}
            className="stat-icon"
            color="var(--warn)"
            style={{ flexShrink: 0 }}
          />
        </div>
        <div className="stat-card red">
          <div className="stat-label">Bloqueadas</div>
          <div className="stat-value red">
            {loading ? "—" : bloqueadasCount}
          </div>
          <ShieldAlert
            size={28}
            className="stat-icon"
            color="var(--err)"
            style={{ flexShrink: 0 }}
          />
        </div>
      </div>

      {/* Barra de Filtros */}
      <div className="filters-bar" style={{ flexWrap: "wrap", marginBottom: 16 }}>
        <div style={{ position: "relative", minWidth: 240, flex: "1 1 240px" }}>
          <Search
            size={14}
            style={{
              position: "absolute",
              left: 10,
              top: "50%",
              transform: "translateY(-50%)",
              color: "var(--text-muted)",
              pointerEvents: "none",
              flexShrink: 0,
            }}
          />
          <input
            type="text"
            className="form-input"
            style={{ paddingLeft: 30 }}
            placeholder="Buscar por nome ou documento..."
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </div>

        <select
          className="form-input"
          value={situacaoFilter}
          onChange={(e) =>
            setSituacaoFilter(
              e.target.value as "TODAS" | "EM_DIA" | "VENCENDO" | "BLOQUEADAS"
            )
          }
          style={{ width: "auto" }}
          title="Filtrar por situação"
        >
          <option value="TODAS">Todas as situações</option>
          <option value="EM_DIA">Em dia (OK, Sem validade)</option>
          <option value="VENCENDO">Vencendo (Aviso, Crítico)</option>
          <option value="BLOQUEADAS">Bloqueadas (Vencida, Suspensa)</option>
        </select>

        <select
          className="form-input"
          value={tipoFilter}
          onChange={(e) =>
            setTipoFilter(
              e.target.value as "TODOS" | "INTEGRADOR" | "CLIENTE_FINAL"
            )
          }
          style={{ width: "auto" }}
          title="Filtrar por tipo"
        >
          <option value="TODOS">Todos os tipos</option>
          <option value="INTEGRADOR">Integrador</option>
          <option value="CLIENTE_FINAL">Cliente final</option>
        </select>
      </div>

      {/* Tabela de Contas */}
      {loading ? (
        <div className="loading-state">
          <div className="spinner" />
        </div>
      ) : loadError && contas.length === 0 ? (
        <div className="empty-state">
          <div>{loadError}</div>
          <button
            type="button"
            className="btn btn-secondary mt-2"
            onClick={() => {
              setLoading(true);
              loadDados();
            }}
          >
            Tentar novamente
          </button>
        </div>
      ) : contasFiltradas.length === 0 ? (
        <div className="empty-state">
          <div>Nenhuma conta encontrada com os filtros selecionados.</div>
          {contas.length === 0 && (
            <button
              type="button"
              className="btn btn-primary mt-2"
              onClick={() => setShowNovoContaModal(true)}
            >
              <Plus size={14} style={{ flexShrink: 0 }} /> Criar nova conta
            </button>
          )}
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Conta</th>
                <th>Tipo</th>
                <th>Plano</th>
                <th>Validade</th>
                <th>Situação</th>
                <th>Máquinas</th>
                <th>Usuários</th>
                <th style={{ width: 80 }}>Ações</th>
              </tr>
            </thead>
            <tbody>
              {contasFiltradas.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => navigate(`/contas/${c.id}`)}
                  style={{ cursor: "pointer" }}
                >
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span
                        style={{
                          fontWeight: 600,
                          color: "var(--text-primary)",
                        }}
                      >
                        {c.nome}
                      </span>
                      {c.plataforma && (
                        <span className="badge muted">Plataforma</span>
                      )}
                    </div>
                    {c.documento && (
                      <div className="text-xs text-muted" style={{ marginTop: 2 }}>
                        {c.documento}
                      </div>
                    )}
                  </td>
                  <td>{TIPO_CONTA_LABEL[c.tipo] ?? c.tipo}</td>
                  <td>{c.plano_nome ?? "—"}</td>
                  <td>{textoValidade(c)}</td>
                  <td>
                    <StatusContaBadge status={c.status} />
                  </td>
                  <td>{c.total_maquinas}</td>
                  <td>{c.total_usuarios}</td>
                  <td>
                    <button
                      type="button"
                      className="btn-icon"
                      title="Entrar na conta"
                      onClick={(e) => {
                        e.stopPropagation();
                        escolherConta(c.id);
                      }}
                    >
                      <LogIn size={15} style={{ flexShrink: 0 }} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Seção Super Administradores da Plataforma */}
      <SuperAdminsSection />

      {/* Modal Planos */}
      {showPlanosModal && (
        <PlanosModal
          onClose={() => setShowPlanosModal(false)}
          onChanged={() => {
            loadDados();
          }}
        />
      )}

      {/* Modal Nova Conta */}
      {showNovoContaModal && (
        <ContaFormModal
          modo="criar"
          planos={planos}
          saving={savingNovo}
          onSave={handleCreateConta}
          onClose={() => setShowNovoContaModal(false)}
        />
      )}
    </>
  );
}
