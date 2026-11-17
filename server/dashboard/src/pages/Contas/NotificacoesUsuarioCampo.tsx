// Notificações por e-mail de um usuário: liga/desliga e, se quiser, só alguns tipos. O e-mail de backup é outro (lista de
// cada máquina/cliente) e não depende disto. O escopo segue as máquinas que o usuário enxerga.
export const TIPOS_EMAIL_NOTIFICACAO: { valor: string; rotulo: string }[] = [
  { valor: "CAMERA_OFFLINE", rotulo: "Câmera offline" },
  { valor: "ONU_OFFLINE", rotulo: "ONU offline (OLT)" },
  { valor: "SINAL_OPTICO", rotulo: "Sinal óptico crítico (OLT)" },
  { valor: "ALARME", rotulo: "Alarmes" },
  { valor: "ANTENA_OFFLINE", rotulo: "Antena offline" },
  { valor: "LICENCA_UNM2000", rotulo: "Licença da UNM2000" },
  { valor: "PERSONALIZADA", rotulo: "Notificações personalizadas" },
];

export default function NotificacoesUsuarioCampo({ ativo, onAtivo, tipos, onTipos }: {
  ativo: boolean;
  onAtivo: (v: boolean) => void;
  tipos: string[] | null; // null = todos os tipos
  onTipos: (v: string[] | null) => void;
}) {
  const marcados = new Set(tipos || []);
  const alternar = (valor: string) =>
    onTipos(marcados.has(valor) ? (tipos || []).filter(t => t !== valor) : [...(tipos || []), valor]);

  return (
    <div className="form-group">
      <label className="form-label">Notificações por e-mail</label>
      <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
        <input type="checkbox" checked={ativo} onChange={e => onAtivo(e.target.checked)} />
        Receber as notificações no e-mail deste usuário
      </label>
      {ativo && (
        <div style={{ marginTop: 8, paddingLeft: 4, display: "grid", gap: 6 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
            <input type="radio" name="notif-tipos" checked={tipos === null} onChange={() => onTipos(null)} />
            Todos os tipos
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
            <input type="radio" name="notif-tipos" checked={tipos !== null} onChange={() => onTipos(tipos ?? [])} />
            Só os tipos marcados
          </label>
          {tipos !== null && (
            <div style={{ display: "grid", gap: 4, paddingLeft: 22 }}>
              {TIPOS_EMAIL_NOTIFICACAO.map(t => (
                <label key={t.valor} style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 13 }}>
                  <input type="checkbox" checked={marcados.has(t.valor)} onChange={() => alternar(t.valor)} />
                  {t.rotulo}
                </label>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="text-xs text-muted" style={{ marginTop: 4 }}>
        Só das máquinas que o usuário enxerga. O e-mail de backup continua sendo a lista de cada máquina/cliente.
        O e-mail de contato da conta recebe sempre.
      </div>
    </div>
  );
}
