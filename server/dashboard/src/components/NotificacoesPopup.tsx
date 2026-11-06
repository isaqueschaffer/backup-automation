import { useEffect, useState } from "react";
import { fetchNotificacoes, NOTIF_POPUP_KEY } from "../api/client";
import { Notificacao } from "../api/types";
import { useAuth } from "../contexts/AuthContext";
import { COR_NOTIFICACAO, ICONE_NOTIFICACAO } from "../utils/notificacoes";
import Modal from "./Modal";

// NOTIF_POPUP_KEY (sessionStorage): marca "já mostrei o pop-up nesta sessão" para não repetir a cada troca de
// página (o Layout remonta por rota); o AuthContext limpa essa chave a cada login, então o pop-up volta a aparecer.

export default function NotificacoesPopup() {
  const { me } = useAuth();
  const [abertas, setAbertas] = useState<Notificacao[] | null>(null);

  useEffect(() => {
    if (!me) return;
    let jaMostrado = false;
    try {
      jaMostrado = sessionStorage.getItem(NOTIF_POPUP_KEY) === "1";
    } catch {
      // sessionStorage indisponível
    }
    if (jaMostrado) return;

    // apenas_popup=true: personalizadas com "mostrar pop-up" desligado não entram aqui (continuam na aba Notificações)
    fetchNotificacoes(true, true)
      .then(setAbertas)
      .catch(() => setAbertas(null))
      .finally(() => {
        try {
          sessionStorage.setItem(NOTIF_POPUP_KEY, "1");
        } catch {
          // sessionStorage indisponível
        }
      });
  }, [me]);

  if (!abertas || abertas.length === 0) return null;

  return (
    <Modal title={`${abertas.length === 1 ? "1 alerta" : `${abertas.length} alertas`} para revisar`} onClose={() => setAbertas([])}>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "4px 0" }}>
        {abertas.map((n) => {
          const Icone = ICONE_NOTIFICACAO[n.tipo];
          const cor = COR_NOTIFICACAO[n.tipo];
          return (
            <div
              key={n.id}
              style={{
                display: "flex", gap: 10, alignItems: "flex-start", padding: "10px 12px",
                border: "1px solid var(--border)", borderLeft: `3px solid ${cor}`,
                borderRadius: "var(--radius-sm)", background: "var(--bg-elevated)",
              }}
            >
              <Icone size={18} color={cor} style={{ flexShrink: 0, marginTop: 2 }} />
              <div>
                <div style={{ fontWeight: 600 }}>{n.titulo}</div>
                <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>{n.mensagem}</div>
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 16 }}>
        <button className="btn btn-primary" onClick={() => setAbertas([])}>Entendi</button>
      </div>
    </Modal>
  );
}
