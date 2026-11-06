import { useCallback, useEffect, useState, FormEvent } from "react";
import { Plus, Edit2, UserX, UserCheck } from "lucide-react";
import {
  fetchUsuariosConta,
  createUsuarioConta,
  updateUsuarioConta,
} from "../../api/contas";
import { Usuario } from "../../api/types";
import Modal from "../../components/Modal";
import { useToast } from "../../components/Toast";
import { fmtDate } from "../../utils/date";
import { apiErrorMessage } from "../../utils/errors";
import { PAPEL_LABEL } from "./contaUi";

interface UsuariosSectionProps {
  contaId?: string;
  podeEditar: boolean;
}

export default function UsuariosSection({ contaId, podeEditar }: UsuariosSectionProps) {
  const { toast } = useToast();

  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal Novo Usuário
  const [showNovoModal, setShowNovoModal] = useState(false);
  const [novoNome, setNovoNome] = useState("");
  const [novoEmail, setNovoEmail] = useState("");
  const [novaSenha, setNovaSenha] = useState("");
  const [novoPapel, setNovoPapel] = useState<"ADMIN" | "LEITURA">("ADMIN");
  const [novoSaving, setNovoSaving] = useState(false);

  // Modal Editar Usuário
  const [editingUsuario, setEditingUsuario] = useState<Usuario | null>(null);
  const [editNome, setEditNome] = useState("");
  const [editPapel, setEditPapel] = useState<"ADMIN" | "LEITURA">("ADMIN");
  const [editSenha, setEditSenha] = useState("");
  const [editSaving, setEditSaving] = useState(false);

  // Ação Ativar/Desativar
  const [toggleBusyId, setToggleBusyId] = useState<string | null>(null);

  const loadUsuarios = useCallback(async () => {
    try {
      setError(null);
      const data = await fetchUsuariosConta(contaId);
      setUsuarios(data);
    } catch (err) {
      setError(apiErrorMessage(err, "Erro ao carregar usuários."));
    } finally {
      setLoading(false);
    }
  }, [contaId]);

  useEffect(() => {
    setLoading(true);
    loadUsuarios();
  }, [loadUsuarios]);

  const abrirNovoModal = () => {
    setNovoNome("");
    setNovoEmail("");
    setNovaSenha("");
    setNovoPapel("ADMIN");
    setShowNovoModal(true);
  };

  const handleCriarUsuario = async (e: FormEvent) => {
    e.preventDefault();
    const nomeTrim = novoNome.trim();
    const emailTrim = novoEmail.trim();

    if (!nomeTrim) {
      toast("Nome é obrigatório.", "error");
      return;
    }
    if (!emailTrim) {
      toast("E-mail é obrigatório.", "error");
      return;
    }
    if (novaSenha.length < 10) {
      toast("A senha deve ter no mínimo 10 caracteres.", "error");
      return;
    }

    setNovoSaving(true);
    try {
      await createUsuarioConta(
        {
          nome: nomeTrim,
          email: emailTrim,
          senha: novaSenha,
          papel: novoPapel,
        },
        contaId
      );
      toast("Usuário criado com sucesso.", "success");
      setShowNovoModal(false);
      await loadUsuarios();
    } catch (err) {
      toast(apiErrorMessage(err, "Erro ao criar usuário."), "error");
    } finally {
      setNovoSaving(false);
    }
  };

  const abrirEditarModal = (u: Usuario) => {
    setEditingUsuario(u);
    setEditNome(u.nome);
    setEditPapel(u.papel === "LEITURA" ? "LEITURA" : "ADMIN");
    setEditSenha("");
  };

  const handleEditarUsuario = async (e: FormEvent) => {
    e.preventDefault();
    if (!editingUsuario) return;

    const nomeTrim = editNome.trim();
    if (!nomeTrim) {
      toast("Nome é obrigatório.", "error");
      return;
    }

    const senhaTrim = editSenha.trim();
    if (senhaTrim && senhaTrim.length < 10) {
      toast("A nova senha deve ter no mínimo 10 caracteres.", "error");
      return;
    }

    setEditSaving(true);
    try {
      await updateUsuarioConta(
        editingUsuario.id,
        {
          nome: nomeTrim,
          papel: editPapel,
          senha: senhaTrim || undefined,
        },
        contaId
      );
      toast("Usuário atualizado com sucesso.", "success");
      setEditingUsuario(null);
      await loadUsuarios();
    } catch (err) {
      toast(apiErrorMessage(err, "Erro ao atualizar usuário."), "error");
    } finally {
      setEditSaving(false);
    }
  };

  const handleToggleAtivo = async (u: Usuario) => {
    const acao = u.ativo ? "desativar" : "reativar";
    const confirmMsg = u.ativo
      ? `Desativar o usuário "${u.nome}"? Ele não conseguirá mais acessar o painel.`
      : `Reativar o usuário "${u.nome}"?`;

    if (!confirm(confirmMsg)) return;

    setToggleBusyId(u.id);
    try {
      await updateUsuarioConta(u.id, { ativo: !u.ativo }, contaId);
      toast(`Usuário ${u.ativo ? "desativado" : "reativado"}.`, "success");
      await loadUsuarios();
    } catch (err) {
      toast(apiErrorMessage(err, `Erro ao ${acao} usuário.`), "error");
    } finally {
      setToggleBusyId(null);
    }
  };

  return (
    <div className="card">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
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
          Usuários
        </h3>
        {podeEditar && (
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={abrirNovoModal}
          >
            <Plus size={14} style={{ flexShrink: 0 }} /> Novo usuário
          </button>
        )}
      </div>

      {loading ? (
        <div className="loading-state">
          <div className="spinner" />
        </div>
      ) : error && usuarios.length === 0 ? (
        <div className="empty-state">
          <div>{error}</div>
          <button
            type="button"
            className="btn btn-secondary mt-2"
            onClick={() => {
              setLoading(true);
              loadUsuarios();
            }}
          >
            Tentar novamente
          </button>
        </div>
      ) : usuarios.length === 0 ? (
        <div className="empty-state">
          <div>Nenhum usuário.</div>
          {podeEditar && (
            <button
              type="button"
              className="btn btn-primary mt-2"
              onClick={abrirNovoModal}
            >
              <Plus size={14} style={{ flexShrink: 0 }} /> Novo usuário
            </button>
          )}
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Nome</th>
                <th>E-mail</th>
                <th>Papel</th>
                <th>Situação</th>
                <th>Último acesso</th>
                {podeEditar && <th>Ações</th>}
              </tr>
            </thead>
            <tbody>
              {usuarios.map((u) => (
                <tr key={u.id}>
                  <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                    {u.nome}
                  </td>
                  <td>{u.email}</td>
                  <td>{PAPEL_LABEL[u.papel] ?? u.papel}</td>
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
                  {podeEditar && (
                    <td>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          className="btn-icon"
                          title="Editar usuário"
                          onClick={() => abrirEditarModal(u)}
                        >
                          <Edit2 size={15} style={{ flexShrink: 0 }} />
                        </button>
                        <button
                          type="button"
                          className="btn-icon"
                          title={u.ativo ? "Desativar usuário" : "Ativar usuário"}
                          onClick={() => handleToggleAtivo(u)}
                          disabled={toggleBusyId === u.id}
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
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showNovoModal && (
        <Modal
          title="Novo usuário"
          onClose={() => {
            if (!novoSaving) setShowNovoModal(false);
          }}
        >
          <form onSubmit={handleCriarUsuario}>
            <div className="form-group">
              <label className="form-label">Nome *</label>
              <input
                className="form-input"
                type="text"
                placeholder="Nome completo"
                value={novoNome}
                onChange={(e) => setNovoNome(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">E-mail *</label>
              <input
                className="form-input"
                type="email"
                placeholder="usuario@empresa.com.br"
                value={novoEmail}
                onChange={(e) => setNovoEmail(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Senha *</label>
              <input
                className="form-input"
                type="password"
                placeholder="Mínimo de 10 caracteres"
                value={novaSenha}
                onChange={(e) => setNovaSenha(e.target.value)}
                required
                minLength={10}
              />
              <div className="text-xs text-muted" style={{ marginTop: 4 }}>
                Mínimo de 10 caracteres. Passe a senha ao usuário por um canal
                seguro.
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Papel *</label>
              <select
                className="form-input"
                value={novoPapel}
                onChange={(e) =>
                  setNovoPapel(e.target.value as "ADMIN" | "LEITURA")
                }
              >
                <option value="ADMIN">Administrador</option>
                <option value="LEITURA">Somente leitura</option>
              </select>
            </div>
            <div
              className="flex gap-3 mt-4"
              style={{ justifyContent: "flex-end" }}
            >
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowNovoModal(false)}
                disabled={novoSaving}
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={novoSaving}
              >
                {novoSaving ? (
                  <span className="spinner spinner-sm" />
                ) : (
                  "Criar usuário"
                )}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {editingUsuario && (
        <Modal
          title="Editar usuário"
          onClose={() => {
            if (!editSaving) setEditingUsuario(null);
          }}
        >
          <form onSubmit={handleEditarUsuario}>
            <div className="form-group">
              <label className="form-label">Nome *</label>
              <input
                className="form-input"
                type="text"
                placeholder="Nome completo"
                value={editNome}
                onChange={(e) => setEditNome(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Papel *</label>
              <select
                className="form-input"
                value={editPapel}
                onChange={(e) =>
                  setEditPapel(e.target.value as "ADMIN" | "LEITURA")
                }
              >
                <option value="ADMIN">Administrador</option>
                <option value="LEITURA">Somente leitura</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Nova senha (opcional)</label>
              <input
                className="form-input"
                type="password"
                placeholder="Deixe em branco para não alterar"
                value={editSenha}
                onChange={(e) => setEditSenha(e.target.value)}
              />
              <div className="text-xs text-muted" style={{ marginTop: 4 }}>
                Deixe em branco para não alterar.
              </div>
            </div>
            <div
              className="flex gap-3 mt-4"
              style={{ justifyContent: "flex-end" }}
            >
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setEditingUsuario(null)}
                disabled={editSaving}
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={editSaving}
              >
                {editSaving ? (
                  <span className="spinner spinner-sm" />
                ) : (
                  "Salvar"
                )}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
