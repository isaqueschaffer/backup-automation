import { FormEvent, useState } from "react";
import Modal from "../../components/Modal";
import { ModoNotificacaoPersonalizada, NotificacaoPersonalizada, NotificacaoPersonalizadaPayload } from "../../api/types";

interface Props {
  inicial?: NotificacaoPersonalizada | null;
  onSalvar: (payload: NotificacaoPersonalizadaPayload) => Promise<void>;
  onClose: () => void;
}

export default function NotificacaoPersonalizadaFormModal({ inicial, onSalvar, onClose }: Props) {
  const [titulo, setTitulo] = useState(inicial?.titulo || "");
  const [mensagem, setMensagem] = useState(inicial?.mensagem || "");
  const [enviarEmail, setEnviarEmail] = useState(inicial?.enviar_email ?? false);
  const [mostrarPopup, setMostrarPopup] = useState(inicial?.mostrar_popup ?? true);
  const [modo, setModo] = useState<ModoNotificacaoPersonalizada>(inicial?.modo || "RECORRENTE");
  const [intervaloDias, setIntervaloDias] = useState(String(inicial?.intervalo_dias ?? "7"));
  const [dataAlvo, setDataAlvo] = useState(inicial?.data_alvo?.slice(0, 10) || "");
  const [diasAntes, setDiasAntes] = useState(String(inicial?.dias_antes ?? "7"));
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  const submeter = async (e: FormEvent) => {
    e.preventDefault();
    setErro("");

    if (!titulo.trim() || !mensagem.trim()) {
      setErro("Preencha o título e a mensagem.");
      return;
    }
    if (!enviarEmail && !mostrarPopup) {
      setErro("Escolha pelo menos um canal: e-mail ou pop-up (ela continua na lista mesmo sem nenhum dos dois marcado).");
      return;
    }
    if (modo === "RECORRENTE" && (!intervaloDias || Number(intervaloDias) < 1)) {
      setErro("Informe a cada quantos dias repetir (1 ou mais).");
      return;
    }
    if (modo === "DATA" && (!dataAlvo || diasAntes === "" || Number(diasAntes) < 0)) {
      setErro("Informe a data e quantos dias antes avisar.");
      return;
    }

    const payload: NotificacaoPersonalizadaPayload = {
      titulo: titulo.trim(),
      mensagem: mensagem.trim(),
      enviar_email: enviarEmail,
      mostrar_popup: mostrarPopup,
      ativo: inicial?.ativo ?? true,
      modo,
      intervalo_dias: modo === "RECORRENTE" ? Number(intervaloDias) : null,
      data_alvo: modo === "DATA" ? dataAlvo : null,
      dias_antes: modo === "DATA" ? Number(diasAntes) : null,
    };

    setSalvando(true);
    try {
      await onSalvar(payload);
    } catch {
      setErro("Não foi possível salvar. Confira os dados e tente de novo.");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <Modal title={inicial ? "Editar notificação" : "Nova notificação personalizada"} onClose={onClose}>
      <form onSubmit={submeter} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div className="form-group" style={{ margin: 0 }}>
          <label className="form-label">Título *</label>
          <input className="form-input" value={titulo} onChange={(e) => setTitulo(e.target.value)} maxLength={255} />
        </div>

        <div className="form-group" style={{ margin: 0 }}>
          <label className="form-label">Mensagem *</label>
          <textarea className="form-input" rows={3} value={mensagem} onChange={(e) => setMensagem(e.target.value)} maxLength={2000} />
        </div>

        <div className="form-group" style={{ margin: 0 }}>
          <label className="form-label">Canais</label>
          <div style={{ display: "flex", gap: 16 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13.5, cursor: "pointer" }}>
              <input type="checkbox" checked={enviarEmail} onChange={(e) => setEnviarEmail(e.target.checked)} />
              Enviar por e-mail
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13.5, cursor: "pointer" }}>
              <input type="checkbox" checked={mostrarPopup} onChange={(e) => setMostrarPopup(e.target.checked)} />
              Mostrar no pop-up ao logar
            </label>
          </div>
          <span style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, display: "block" }}>
            Independente dos canais, ela sempre aparece na lista abaixo.
          </span>
        </div>

        <div className="form-group" style={{ margin: 0 }}>
          <label className="form-label">Frequência</label>
          <div style={{ display: "flex", gap: 16, marginBottom: 8 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13.5, cursor: "pointer" }}>
              <input type="radio" name="modo" checked={modo === "RECORRENTE"} onChange={() => setModo("RECORRENTE")} />
              A cada X dias
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13.5, cursor: "pointer" }}>
              <input type="radio" name="modo" checked={modo === "DATA"} onChange={() => setModo("DATA")} />
              Faltando X dias para uma data
            </label>
          </div>

          {modo === "RECORRENTE" ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 13.5 }}>A cada</span>
              <input className="form-input" type="number" min={1} max={365} style={{ width: 80 }}
                value={intervaloDias} onChange={(e) => setIntervaloDias(e.target.value)} />
              <span style={{ fontSize: 13.5 }}>dia(s)</span>
            </div>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span style={{ fontSize: 13.5 }}>Avisar</span>
              <input className="form-input" type="number" min={0} max={365} style={{ width: 80 }}
                value={diasAntes} onChange={(e) => setDiasAntes(e.target.value)} />
              <span style={{ fontSize: 13.5 }}>dia(s) antes de</span>
              <input className="form-input" type="date" style={{ width: 160 }}
                value={dataAlvo} onChange={(e) => setDataAlvo(e.target.value)} />
            </div>
          )}
          {modo === "DATA" && (
            <span style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, display: "block" }}>
              Depois que a data passar, continua avisando que venceu até você desativar ou apagar.
            </span>
          )}
        </div>

        {erro && <div style={{ color: "var(--err)", fontSize: 13 }}>{erro}</div>}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
          <button type="button" className="btn btn-secondary" onClick={onClose}>Cancelar</button>
          <button type="submit" className="btn btn-primary" disabled={salvando}>
            {salvando ? <span className="spinner spinner-sm" /> : "Salvar"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
