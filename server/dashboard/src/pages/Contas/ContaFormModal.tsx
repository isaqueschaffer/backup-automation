import { useState, useEffect, FormEvent } from "react";
import { NovaContaPayload, EditarContaPayload } from "../../api/contas";
import { ContaDetalhe, Plano, TipoConta } from "../../api/types";
import Modal from "../../components/Modal";
import { useToast } from "../../components/Toast";
import { diaLocalDaValidade, fimDoDiaBrasilia } from "./contaUi";

interface ContaFormModalProps {
  modo: "criar" | "editar";
  conta?: ContaDetalhe;
  planos: Plano[];
  saving: boolean;
  onSave: (dados: NovaContaPayload | Partial<EditarContaPayload>) => void;
  onClose: () => void;
}

export default function ContaFormModal({
  modo,
  conta,
  planos,
  saving,
  onSave,
  onClose,
}: ContaFormModalProps) {
  const { toast } = useToast();

  // Campos comuns
  const [nome, setNome] = useState(conta?.nome ?? "");
  const [tipo, setTipo] = useState<TipoConta>(conta?.tipo ?? "INTEGRADOR");
  const [documento, setDocumento] = useState(conta?.documento ?? "");
  const [emailContato, setEmailContato] = useState(conta?.email_contato ?? "");
  const [telefone, setTelefone] = useState(conta?.telefone ?? "");
  const [observacoes, setObservacoes] = useState(conta?.observacoes ?? "");

  // Campos exclusivos do modo "criar"
  const [planoId, setPlanoId] = useState("");
  const [adminNome, setAdminNome] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminSenha, setAdminSenha] = useState("");

  // Campo exclusivo do modo "editar"
  const [validade, setValidade] = useState(diaLocalDaValidade(conta?.expira_em));

  const planosAtivos = planos.filter((p) => p.ativo);

  useEffect(() => {
    if (modo === "criar" && !planoId && planosAtivos.length > 0) {
      setPlanoId(planosAtivos[0].id);
    }
  }, [modo, planoId, planosAtivos]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();

    const nomeTrim = nome.trim();
    if (!nomeTrim) {
      toast("Nome da conta é obrigatório.", "error");
      return;
    }

    if (modo === "criar") {
      if (!planoId) {
        toast("Selecione um plano.", "error");
        return;
      }
      const adminNomeTrim = adminNome.trim();
      if (!adminNomeTrim) {
        toast("Nome do administrador é obrigatório.", "error");
        return;
      }
      const adminEmailTrim = adminEmail.trim();
      if (!adminEmailTrim) {
        toast("E-mail do administrador é obrigatório.", "error");
        return;
      }
      if (adminSenha.length < 10) {
        toast("A senha do administrador deve ter no mínimo 10 caracteres.", "error");
        return;
      }

      const payload: NovaContaPayload = {
        nome: nomeTrim,
        tipo,
        documento: documento.trim() || null,
        email_contato: emailContato.trim() || null,
        telefone: telefone.trim() || null,
        observacoes: observacoes.trim() || null,
        plano_id: planoId,
        admin: {
          nome: adminNomeTrim,
          email: adminEmailTrim,
          senha: adminSenha,
        },
      };
      onSave(payload);
    } else {
      const payload: Partial<EditarContaPayload> = {
        nome: nomeTrim,
        tipo,
        documento: documento.trim() || null,
        email_contato: emailContato.trim() || null,
        telefone: telefone.trim() || null,
        observacoes: observacoes.trim() || null,
      };

      const dataOriginal = diaLocalDaValidade(conta?.expira_em);
      if (!conta?.plataforma && validade && validade !== dataOriginal) {
        payload.expira_em = fimDoDiaBrasilia(validade);
      }

      onSave(payload);
    }
  };

  return (
    <Modal
      title={modo === "criar" ? "Nova conta" : "Editar conta"}
      onClose={() => {
        if (!saving) onClose();
      }}
      width={580}
    >
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label">Nome da conta *</label>
          <input
            type="text"
            className="form-input"
            placeholder="Ex.: Trilan Segurança, Filial Centro"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            required
          />
        </div>

        <div className="form-group">
          <label className="form-label">Tipo de conta *</label>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 12,
            }}
          >
            <button
              type="button"
              onClick={() => setTipo("INTEGRADOR")}
              style={{
                padding: "12px 14px",
                borderRadius: "var(--radius, 8px)",
                border:
                  tipo === "INTEGRADOR"
                    ? "2px solid var(--primary)"
                    : "1px solid var(--border)",
                background:
                  tipo === "INTEGRADOR" ? "var(--surface-2)" : "var(--surface)",
                cursor: "pointer",
                textAlign: "left",
                display: "flex",
                flexDirection: "column",
                gap: 4,
                transition: "all 0.15s ease",
              }}
            >
              <div
                style={{
                  fontWeight: 600,
                  fontSize: 14,
                  color:
                    tipo === "INTEGRADOR"
                      ? "var(--primary)"
                      : "var(--text-primary)",
                }}
              >
                Integrador
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: "var(--text-muted)",
                  lineHeight: 1.35,
                }}
              >
                Tem clientes, e cada cliente tem máquinas.
              </div>
            </button>

            <button
              type="button"
              onClick={() => setTipo("CLIENTE_FINAL")}
              style={{
                padding: "12px 14px",
                borderRadius: "var(--radius, 8px)",
                border:
                  tipo === "CLIENTE_FINAL"
                    ? "2px solid var(--primary)"
                    : "1px solid var(--border)",
                background:
                  tipo === "CLIENTE_FINAL"
                    ? "var(--surface-2)"
                    : "var(--surface)",
                cursor: "pointer",
                textAlign: "left",
                display: "flex",
                flexDirection: "column",
                gap: 4,
                transition: "all 0.15s ease",
              }}
            >
              <div
                style={{
                  fontWeight: 600,
                  fontSize: 14,
                  color:
                    tipo === "CLIENTE_FINAL"
                      ? "var(--primary)"
                      : "var(--text-primary)",
                }}
              >
                Cliente final
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: "var(--text-muted)",
                  lineHeight: 1.35,
                }}
              >
                Organiza as máquinas em setores.
              </div>
            </button>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">CPF / CNPJ</label>
          <input
            type="text"
            className="form-input"
            placeholder="00.000.000/0000-00"
            value={documento}
            onChange={(e) => setDocumento(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label className="form-label">E-mail de contato</label>
          <input
            type="email"
            className="form-input"
            placeholder="financeiro@empresa.com.br"
            value={emailContato}
            onChange={(e) => setEmailContato(e.target.value)}
          />
          <div className="text-xs text-muted" style={{ marginTop: 4 }}>
            Recebe os avisos de vencimento.
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Telefone</label>
          <input
            type="text"
            className="form-input"
            placeholder="(11) 99999-9999"
            value={telefone}
            onChange={(e) => setTelefone(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Observações</label>
          <textarea
            className="form-input"
            rows={3}
            placeholder="Informações adicionais da conta..."
            value={observacoes}
            onChange={(e) => setObservacoes(e.target.value)}
          />
        </div>

        {modo === "criar" && (
          <>
            <div className="form-group">
              <label className="form-label">Plano *</label>
              <select
                className="form-input"
                value={planoId}
                onChange={(e) => setPlanoId(e.target.value)}
                required
              >
                <option value="">Selecione um plano...</option>
                {planosAtivos.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nome} — {p.duracao_dias} dias
                  </option>
                ))}
              </select>
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
                Administrador da conta
              </h4>

              <div className="form-group">
                <label className="form-label">Nome do administrador *</label>
                <input
                  type="text"
                  className="form-input"
                  placeholder="Nome completo do administrador"
                  value={adminNome}
                  onChange={(e) => setAdminNome(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">E-mail do administrador *</label>
                <input
                  type="email"
                  className="form-input"
                  placeholder="admin@empresa.com.br"
                  value={adminEmail}
                  onChange={(e) => setAdminEmail(e.target.value)}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">Senha do administrador *</label>
                <input
                  type="password"
                  className="form-input"
                  placeholder="Mínimo de 10 caracteres"
                  value={adminSenha}
                  onChange={(e) => setAdminSenha(e.target.value)}
                  required
                  minLength={10}
                />
                <div className="text-xs text-muted" style={{ marginTop: 4 }}>
                  Mínimo de 10 caracteres. A validade começa hoje e dura o período do plano.
                </div>
              </div>
            </div>
          </>
        )}

        {modo === "editar" && !conta?.plataforma && (
          <div className="form-group">
            <label className="form-label">Validade</label>
            <input
              type="date"
              className="form-input"
              value={validade}
              onChange={(e) => setValidade(e.target.value)}
            />
            <div className="text-xs text-muted" style={{ marginTop: 4 }}>
              Ajuste manual da validade da conta (término no fim do dia selecionado).
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
            onClick={onClose}
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
            ) : modo === "criar" ? (
              "Criar conta"
            ) : (
              "Salvar alterações"
            )}
          </button>
        </div>
      </form>
    </Modal>
  );
}
