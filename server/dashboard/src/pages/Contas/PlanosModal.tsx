import { useCallback, useEffect, useState, FormEvent } from "react";
import { Edit2, Check, X, Plus, Ban, CheckCircle2 } from "lucide-react";
import { fetchPlanos, createPlano, updatePlano } from "../../api/contas";
import { Plano } from "../../api/types";
import Modal from "../../components/Modal";
import { useToast } from "../../components/Toast";
import { apiErrorMessage } from "../../utils/errors";

interface PlanosModalProps {
  onClose: () => void;
  onChanged: () => void;
}

export default function PlanosModal({ onClose, onChanged }: PlanosModalProps) {
  const { toast } = useToast();

  const [planos, setPlanos] = useState<Plano[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Edição em linha
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editNome, setEditNome] = useState("");
  const [editDias, setEditDias] = useState("");
  const [salvandoId, setSalvandoId] = useState<string | null>(null);

  // Ativar / Desativar
  const [togglingId, setTogglingId] = useState<string | null>(null);

  // Criação de novo plano
  const [novoNome, setNovoNome] = useState("");
  const [novoDias, setNovoDias] = useState("");
  const [criando, setCriando] = useState(false);

  const loadPlanos = useCallback(async () => {
    try {
      setError(null);
      const data = await fetchPlanos();
      setPlanos(data);
    } catch (err) {
      setError(apiErrorMessage(err, "Erro ao carregar planos."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPlanos();
  }, [loadPlanos]);

  const iniciarEdicao = (p: Plano) => {
    setEditingId(p.id);
    setEditNome(p.nome);
    setEditDias(String(p.duracao_dias));
  };

  const cancelarEdicao = () => {
    setEditingId(null);
    setEditNome("");
    setEditDias("");
  };

  const handleSalvarEdicao = async (id: string) => {
    const nomeTrim = editNome.trim();
    const diasNum = parseInt(editDias, 10);

    if (!nomeTrim) {
      toast("Nome do plano é obrigatório.", "error");
      return;
    }
    if (isNaN(diasNum) || diasNum <= 0) {
      toast("A duração em dias deve ser maior que zero.", "error");
      return;
    }

    setSalvandoId(id);
    try {
      await updatePlano(id, { nome: nomeTrim, duracao_dias: diasNum });
      toast("Plano atualizado com sucesso.", "success");
      cancelarEdicao();
      await loadPlanos();
      onChanged();
    } catch (err) {
      toast(apiErrorMessage(err, "Erro ao atualizar plano."), "error");
    } finally {
      setSalvandoId(null);
    }
  };

  const handleToggleAtivo = async (p: Plano) => {
    const confirmMsg = p.ativo
      ? `Desativar o plano "${p.nome}"? Ele não aparecerá mais para novas contas ou renovações.`
      : `Ativar o plano "${p.nome}"?`;

    if (!confirm(confirmMsg)) return;

    setTogglingId(p.id);
    try {
      await updatePlano(p.id, { ativo: !p.ativo });
      toast(
        `Plano ${p.ativo ? "desativado" : "ativado"} com sucesso.`,
        "success"
      );
      await loadPlanos();
      onChanged();
    } catch (err) {
      toast(
        apiErrorMessage(
          err,
          `Erro ao ${p.ativo ? "desativar" : "ativar"} plano.`
        ),
        "error"
      );
    } finally {
      setTogglingId(null);
    }
  };

  const handleCriarPlano = async (e: FormEvent) => {
    e.preventDefault();

    const nomeTrim = novoNome.trim();
    const diasNum = parseInt(novoDias, 10);

    if (!nomeTrim) {
      toast("Nome do plano é obrigatório.", "error");
      return;
    }
    if (isNaN(diasNum) || diasNum <= 0) {
      toast("A duração em dias deve ser maior que zero.", "error");
      return;
    }

    setCriando(true);
    try {
      await createPlano({ nome: nomeTrim, duracao_dias: diasNum });
      toast("Plano criado com sucesso.", "success");
      setNovoNome("");
      setNovoDias("");
      await loadPlanos();
      onChanged();
    } catch (err) {
      toast(apiErrorMessage(err, "Erro ao criar plano."), "error");
    } finally {
      setCriando(false);
    }
  };

  return (
    <Modal title="Planos de assinatura" onClose={onClose} width={680}>
      {loading ? (
        <div className="loading-state">
          <div className="spinner" />
        </div>
      ) : error && planos.length === 0 ? (
        <div className="empty-state">
          <div>{error}</div>
          <button
            type="button"
            className="btn btn-secondary mt-2"
            onClick={() => {
              setLoading(true);
              loadPlanos();
            }}
          >
            Tentar novamente
          </button>
        </div>
      ) : (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Nome</th>
                  <th>Duração</th>
                  <th>Situação</th>
                  <th style={{ width: 100 }}>Ações</th>
                </tr>
              </thead>
              <tbody>
                {planos.length === 0 ? (
                  <tr>
                    <td
                      colSpan={4}
                      style={{ textAlign: "center", color: "var(--text-muted)" }}
                    >
                      Nenhum plano cadastrado.
                    </td>
                  </tr>
                ) : (
                  planos.map((p) => {
                    const emEdicao = editingId === p.id;
                    return (
                      <tr key={p.id}>
                        <td>
                          {emEdicao ? (
                            <input
                              type="text"
                              className="form-input"
                              value={editNome}
                              onChange={(e) => setEditNome(e.target.value)}
                              disabled={salvandoId === p.id}
                              style={{ padding: "4px 8px", fontSize: 13 }}
                              required
                            />
                          ) : (
                            <span
                              style={{
                                fontWeight: 600,
                                color: "var(--text-primary)",
                              }}
                            >
                              {p.nome}
                            </span>
                          )}
                        </td>
                        <td>
                          {emEdicao ? (
                            <input
                              type="number"
                              min={1}
                              className="form-input"
                              value={editDias}
                              onChange={(e) => setEditDias(e.target.value)}
                              disabled={salvandoId === p.id}
                              style={{
                                width: 90,
                                padding: "4px 8px",
                                fontSize: 13,
                              }}
                              required
                            />
                          ) : (
                            <span>
                              {p.duracao_dias}{" "}
                              {p.duracao_dias === 1 ? "dia" : "dias"}
                            </span>
                          )}
                        </td>
                        <td>
                          {p.ativo ? (
                            <span className="badge ok">Ativo</span>
                          ) : (
                            <span className="badge muted">Inativo</span>
                          )}
                        </td>
                        <td>
                          <div
                            className="flex gap-2"
                            style={{ alignItems: "center" }}
                          >
                            {emEdicao ? (
                              <>
                                <button
                                  type="button"
                                  className="btn-icon"
                                  title="Salvar alterações"
                                  disabled={salvandoId === p.id}
                                  onClick={() => handleSalvarEdicao(p.id)}
                                  style={{ color: "var(--ok)" }}
                                >
                                  {salvandoId === p.id ? (
                                    <span className="spinner spinner-sm" />
                                  ) : (
                                    <Check
                                      size={16}
                                      style={{ flexShrink: 0 }}
                                    />
                                  )}
                                </button>
                                <button
                                  type="button"
                                  className="btn-icon"
                                  title="Cancelar"
                                  disabled={salvandoId === p.id}
                                  onClick={cancelarEdicao}
                                >
                                  <X size={16} style={{ flexShrink: 0 }} />
                                </button>
                              </>
                            ) : (
                              <>
                                <button
                                  type="button"
                                  className="btn-icon"
                                  title="Editar plano"
                                  disabled={togglingId === p.id}
                                  onClick={() => iniciarEdicao(p)}
                                >
                                  <Edit2 size={15} style={{ flexShrink: 0 }} />
                                </button>
                                <button
                                  type="button"
                                  className="btn-icon"
                                  title={
                                    p.ativo
                                      ? "Desativar plano"
                                      : "Ativar plano"
                                  }
                                  disabled={togglingId === p.id}
                                  onClick={() => handleToggleAtivo(p)}
                                  style={
                                    p.ativo
                                      ? { color: "var(--err)" }
                                      : { color: "var(--ok)" }
                                  }
                                >
                                  {togglingId === p.id ? (
                                    <span className="spinner spinner-sm" />
                                  ) : p.ativo ? (
                                    <Ban
                                      size={15}
                                      style={{ flexShrink: 0 }}
                                    />
                                  ) : (
                                    <CheckCircle2
                                      size={15}
                                      style={{ flexShrink: 0 }}
                                    />
                                  )}
                                </button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <div
            style={{
              marginTop: 20,
              paddingTop: 16,
              borderTop: "1px solid var(--border)",
            }}
          >
            <h4
              style={{
                margin: "0 0 12px 0",
                fontSize: 14,
                fontWeight: 600,
                color: "var(--text-primary)",
              }}
            >
              Novo plano
            </h4>
            <form
              onSubmit={handleCriarPlano}
              style={{
                display: "flex",
                gap: 12,
                alignItems: "flex-end",
                flexWrap: "wrap",
              }}
            >
              <div style={{ flex: "2 1 200px" }}>
                <label className="form-label">Nome do plano *</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Ex.: Mensal, Trimestral, Anual"
                  value={novoNome}
                  onChange={(e) => setNovoNome(e.target.value)}
                  required
                />
              </div>

              <div style={{ flex: "1 1 120px" }}>
                <label className="form-label">Duração (dias) *</label>
                <input
                  type="number"
                  min={1}
                  className="form-input"
                  placeholder="30"
                  value={novoDias}
                  onChange={(e) => setNovoDias(e.target.value)}
                  required
                />
              </div>

              <div>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={criando}
                  style={{ height: 38 }}
                >
                  {criando ? (
                    <span className="spinner spinner-sm" />
                  ) : (
                    <>
                      <Plus size={15} style={{ flexShrink: 0 }} /> Adicionar
                    </>
                  )}
                </button>
              </div>
            </form>
            <div className="text-xs text-muted" style={{ marginTop: 8 }}>
              Plano inativo não aparece para novas contas nem renovações; as contas que já o usam não mudam.
            </div>
          </div>

          <div
            className="flex mt-4"
            style={{ justifyContent: "flex-end" }}
          >
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
            >
              Fechar
            </button>
          </div>
        </>
      )}
    </Modal>
  );
}
