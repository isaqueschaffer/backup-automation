import { useRef, useState } from "react";
import { Copy, Link2, RefreshCw, Trash2 } from "lucide-react";
import Modal from "../../components/Modal";
import { useToast } from "../../components/Toast";
import { apiErrorMessage } from "../../utils/errors";
import { fmtDate, localDateStr } from "../../utils/date";
import { Compartilhamento, LinkGerado } from "./types";
import {
  createShareLink,
  revokeShareLink,
  updateShareLink,
} from "../../api/dashboards";

interface Props {
  customerId: string;
  compartilhamento: Compartilhamento;
  onChange: (c: Compartilhamento) => void;
  onClose: () => void;
}

// Modal para gerenciamento do link público de compartilhamento do dashboard
export default function SharePanel({
  customerId,
  compartilhamento,
  onChange,
  onClose,
}: Props) {
  const { toast } = useToast();
  const inputRef = useRef<HTMLInputElement>(null);

  const [comp, setComp] = useState<Compartilhamento>(compartilhamento);
  const [linkGerado, setLinkGerado] = useState<LinkGerado | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [validade, setValidade] = useState<"nenhuma" | "7" | "30" | "90" | "data">("nenhuma");
  const [dataValidade, setDataValidade] = useState<string>("");
  const [permiteEdicao, setPermiteEdicao] = useState<boolean>(false);

  const calcularExpiracao = (): string | null | undefined => {
    if (validade === "nenhuma") {
      return null;
    }
    if (validade === "7" || validade === "30" || validade === "90") {
      const dias = Number(validade);
      return new Date(Date.now() + dias * 86400000).toISOString();
    }
    if (validade === "data") {
      if (!dataValidade) {
        toast("Escolha uma data de validade futura.", "error");
        return undefined;
      }
      const d = new Date(`${dataValidade}T23:59:59`);
      if (Number.isNaN(d.getTime()) || d.getTime() <= Date.now()) {
        toast("Escolha uma data de validade futura.", "error");
        return undefined;
      }
      return d.toISOString();
    }
    return null;
  };

  const handleCopiar = async () => {
    if (!linkGerado) return;
    const url = linkGerado.url || `${window.location.origin}${linkGerado.caminho}`;
    try {
      await navigator.clipboard.writeText(url);
      toast("Link copiado.", "success");
    } catch {
      if (inputRef.current) {
        inputRef.current.select();
      }
      toast("Não foi possível copiar automaticamente. Use Ctrl+C para copiar.", "info");
    }
  };

  const handleGerarLink = async () => {
    const expira = calcularExpiracao();
    if (expira === undefined) return;
    setOcupado(true);
    try {
      const res = await createShareLink(customerId, {
        expira_em: expira,
        permite_edicao: permiteEdicao,
      });
      setLinkGerado(res);
      setComp(res.compartilhamento);
      onChange(res.compartilhamento);
    } catch (err: unknown) {
      toast(apiErrorMessage(err, "Erro ao gerar link de compartilhamento."), "error");
    } finally {
      setOcupado(false);
    }
  };

  const handleToggleAtivo = async (ativo: boolean) => {
    setOcupado(true);
    try {
      const res = await updateShareLink(customerId, { ativo });
      setComp(res);
      onChange(res);
    } catch (err: unknown) {
      toast(apiErrorMessage(err, "Erro ao alterar status do link."), "error");
    } finally {
      setOcupado(false);
    }
  };

  const handleTogglePermiteEdicao = async (permite_edicao: boolean) => {
    setOcupado(true);
    try {
      const res = await updateShareLink(customerId, { permite_edicao });
      setComp(res);
      onChange(res);
    } catch (err: unknown) {
      toast(apiErrorMessage(err, "Erro ao alterar permissão de edição."), "error");
    } finally {
      setOcupado(false);
    }
  };

  const handleAplicarValidade = async () => {
    const expira = calcularExpiracao();
    if (expira === undefined) return;
    setOcupado(true);
    try {
      let res: Compartilhamento;
      if (expira === null) {
        res = await updateShareLink(customerId, { limpar_expiracao: true });
      } else {
        res = await updateShareLink(customerId, { expira_em: expira });
      }
      setComp(res);
      onChange(res);
      toast("Validade do link atualizada.", "success");
    } catch (err: unknown) {
      toast(apiErrorMessage(err, "Erro ao alterar validade do link."), "error");
    } finally {
      setOcupado(false);
    }
  };

  const handleGerarNovoLink = async () => {
    if (!confirm("Gerar um novo link? O link atual deixará de funcionar.")) return;
    const expira = calcularExpiracao();
    if (expira === undefined) return;
    setOcupado(true);
    try {
      const res = await createShareLink(customerId, {
        expira_em: expira,
        permite_edicao: comp.permite_edicao,
      });
      setLinkGerado(res);
      setComp(res.compartilhamento);
      onChange(res.compartilhamento);
    } catch (err: unknown) {
      toast(apiErrorMessage(err, "Erro ao gerar novo link."), "error");
    } finally {
      setOcupado(false);
    }
  };

  const handleRevogarLink = async () => {
    if (!confirm("Revogar o link? Quem o possui perderá o acesso imediatamente.")) return;
    setOcupado(true);
    try {
      await revokeShareLink(customerId);
      setLinkGerado(null);
      const revogado: Compartilhamento = {
        ativo: false,
        tem_link: false,
        expira_em: null,
        permite_edicao: false,
        criado_em: null,
        ultimo_acesso: null,
        expirado: false,
      };
      setComp(revogado);
      onChange(revogado);
    } catch (err: unknown) {
      toast(apiErrorMessage(err, "Erro ao revogar link."), "error");
    } finally {
      setOcupado(false);
    }
  };

  return (
    <Modal title="Compartilhar dashboard" onClose={onClose} width={600}>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {/* Aviso de privacidade */}
        <div style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.5 }}>
          Quem tiver o link vê somente os componentes e os equipamentos escolhidos neste dashboard, sem acesso a nenhuma outra área do sistema.
        </div>

        {/* Sem link existente */}
        {!comp.tem_link && linkGerado === null && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <label style={{ fontSize: 13, fontWeight: 500, color: "var(--text-secondary)" }}>
                Validade do link
              </label>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                <select
                  className="form-input"
                  value={validade}
                  onChange={(e) =>
                    setValidade(e.target.value as "nenhuma" | "7" | "30" | "90" | "data")
                  }
                  disabled={ocupado}
                  style={{ flex: 1, minWidth: 160 }}
                >
                  <option value="nenhuma">Sem validade</option>
                  <option value="7">7 dias</option>
                  <option value="30">30 dias</option>
                  <option value="90">90 dias</option>
                  <option value="data">Escolher data</option>
                </select>
                {validade === "data" && (
                  <input
                    type="date"
                    className="form-input"
                    min={localDateStr()}
                    value={dataValidade}
                    onChange={(e) => setDataValidade(e.target.value)}
                    disabled={ocupado}
                    style={{ width: "auto" }}
                  />
                )}
              </div>
            </div>

            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                cursor: ocupado ? "not-allowed" : "pointer",
                fontSize: 13,
              }}
            >
              <input
                type="checkbox"
                checked={permiteEdicao}
                onChange={(e) => setPermiteEdicao(e.target.checked)}
                disabled={ocupado}
              />
              <span>
                Permitir que quem recebe o link personalize o dashboard (reordenar, adicionar e remover componentes)
              </span>
            </label>

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 4 }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleGerarLink}
                disabled={ocupado}
              >
                {ocupado ? (
                  <span className="spinner spinner-sm" />
                ) : (
                  <Link2 size={14} style={{ flexShrink: 0 }} />
                )}{" "}
                Gerar link
              </button>
            </div>
          </div>
        )}

        {/* Link recém-gerado */}
        {linkGerado && (
          <div
            style={{
              border: "1px solid var(--accent)",
              background: "var(--surface-2)",
              borderRadius: 8,
              padding: 14,
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            <div style={{ display: "flex", gap: 8 }}>
              <input
                ref={inputRef}
                readOnly
                className="form-input"
                value={linkGerado.url || `${window.location.origin}${linkGerado.caminho}`}
                style={{ flex: 1 }}
              />
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleCopiar}
                disabled={ocupado}
              >
                <Copy size={14} style={{ flexShrink: 0 }} /> Copiar
              </button>
            </div>
            <div
              style={{
                fontSize: 12,
                color: "var(--warn)",
                lineHeight: 1.4,
                fontWeight: 500,
              }}
            >
              Copie agora: por segurança este link não será exibido novamente. Se perder, gere outro — o anterior deixa de funcionar.
            </div>
          </div>
        )}

        {/* Com link existente */}
        {comp.tem_link && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 12,
                fontSize: 13,
                color: "var(--text-secondary)",
                paddingBottom: 12,
                borderBottom: "1px solid var(--border)",
              }}
            >
              {comp.expirado ? (
                <span className="badge err">Expirado</span>
              ) : comp.ativo ? (
                <span className="badge ok">Ativo</span>
              ) : (
                <span className="badge warn">Desativado</span>
              )}
              <span>Validade: {fmtDate(comp.expira_em, { empty: "Sem validade" })}</span>
              <span>Último acesso: {fmtDate(comp.ultimo_acesso, { empty: "Nunca" })}</span>
              <span>Criado em {fmtDate(comp.criado_em)}</span>
            </div>

            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Por segurança, o link atual não pode ser exibido novamente. Para obter um endereço, gere um novo link (o atual deixará de funcionar).
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  cursor: ocupado ? "not-allowed" : "pointer",
                  fontSize: 13,
                }}
              >
                <input
                  type="checkbox"
                  checked={comp.ativo}
                  disabled={ocupado}
                  onChange={(e) => handleToggleAtivo(e.target.checked)}
                />
                <span>Link ativo</span>
              </label>

              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  cursor: ocupado ? "not-allowed" : "pointer",
                  fontSize: 13,
                }}
              >
                <input
                  type="checkbox"
                  checked={comp.permite_edicao}
                  disabled={ocupado}
                  onChange={(e) => handleTogglePermiteEdicao(e.target.checked)}
                />
                <span>Permitir que quem recebe o link personalize o dashboard</span>
              </label>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <label style={{ fontSize: 13, fontWeight: 500, color: "var(--text-secondary)" }}>
                Alterar validade
              </label>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                <select
                  className="form-input"
                  value={validade}
                  onChange={(e) =>
                    setValidade(e.target.value as "nenhuma" | "7" | "30" | "90" | "data")
                  }
                  disabled={ocupado}
                  style={{ flex: 1, minWidth: 160 }}
                >
                  <option value="nenhuma">Sem validade</option>
                  <option value="7">7 dias</option>
                  <option value="30">30 dias</option>
                  <option value="90">90 dias</option>
                  <option value="data">Escolher data</option>
                </select>
                {validade === "data" && (
                  <input
                    type="date"
                    className="form-input"
                    min={localDateStr()}
                    value={dataValidade}
                    onChange={(e) => setDataValidade(e.target.value)}
                    disabled={ocupado}
                    style={{ width: "auto" }}
                  />
                )}
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleAplicarValidade}
                  disabled={ocupado}
                >
                  Aplicar
                </button>
              </div>
            </div>

            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                paddingTop: 12,
                borderTop: "1px solid var(--border)",
              }}
            >
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleGerarNovoLink}
                disabled={ocupado}
              >
                <RefreshCw size={14} style={{ flexShrink: 0 }} /> Gerar novo link
              </button>

              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleRevogarLink}
                disabled={ocupado}
                style={{ color: "var(--err)" }}
              >
                <Trash2 size={14} style={{ flexShrink: 0 }} /> Revogar link
              </button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
