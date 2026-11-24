import Modal from "../../../../components/Modal";
import { useRotulos } from "../../../../contexts/AuthContext";

// Campos editáveis da máquina (email_to como texto separado por vírgula).
// Cliente e posição na fila são alterados na tela do Cliente.
export interface EditMachineForm {
  name: string;
  backup_hour: number;
  backup_minute: number;
  email_to: string;
  zip_password: string;
  // Onde o agente roda; o cliente pode trocar (ex.: tirou o Windows e passou a usar o MikroTik)
  agente_tipo: "WINDOWS" | "MIKROTIK";
}

export default function EditMachineModal({ form, setForm, agenteTipoAtual, customerName, emailCustomerName, saving, onSave, onClose }: {
  form: EditMachineForm;
  // Tipo salvo hoje, para avisar o que muda quando o usuário troca
  agenteTipoAtual: "WINDOWS" | "MIKROTIK";
  setForm: React.Dispatch<React.SetStateAction<EditMachineForm>>;
  // Nome do cliente quando o horário vem dele (campo travado); null = horário próprio
  customerName: string | null;
  // Nome do cliente quando os e-mails vêm dele (campo travado e não enviado no PUT); null = e-mails próprios
  emailCustomerName: string | null;
  saving: boolean;
  onSave: () => void;
  onClose: () => void;
}) {
  const { singularMin } = useRotulos();
  const locked = customerName !== null;
  const emailLocked = emailCustomerName !== null;
  return (
    <Modal title="Editar Máquina" onClose={onClose}>
      <div className="form-group">
        <label className="form-label">Nome</label>
        <input className="form-input" value={form.name}
          onChange={e => setForm({ ...form, name: e.target.value })} />
      </div>
      <div className="form-group">
        <label className="form-label">Onde o agente roda</label>
        <select className="form-input" value={form.agente_tipo}
          onChange={e => setForm({ ...form, agente_tipo: e.target.value as EditMachineForm["agente_tipo"] })}>
          <option value="WINDOWS">Na própria máquina (Windows)</option>
          <option value="MIKROTIK">No MikroTik (container Linux)</option>
        </select>
        <div className="text-xs text-muted" style={{ marginTop: 4 }}>
          {form.agente_tipo === "MIKROTIK"
            ? "O agente acessa cada equipamento pelo IP dele: informe o IP em todos os equipamentos (UNM2000 e Digifort também acessam a pasta pela rede)."
            : "O agente roda na própria máquina e lê as pastas locais."}
        </div>
        {form.agente_tipo !== agenteTipoAtual && (
          <div className="text-xs" style={{ marginTop: 6, color: "var(--warning, #b45309)" }}>
            {form.agente_tipo === "MIKROTIK"
              ? "Ao trocar para o MikroTik: instale o agente no roteador usando o Client ID e a API Key desta máquina (o histórico continua aqui), revise os equipamentos (IP de cada um; UNM2000/Digifort com o IP da máquina onde está a pasta) e lembre que no MikroTik só o backup de UNM2000 e Digifort por pasta de rede roda; NVR, PABX e outros que gravam arquivo ficam sem backup."
              : "Ao trocar para o Windows: instale o agente na máquina usando o Client ID e a API Key desta máquina (o histórico continua aqui) e revise os equipamentos (UNM2000/Digifort podem voltar a usar a pasta local)."}
          </div>
        )}
      </div>
      <div className="form-group">
        <label className="form-label">Horário do Backup Automático</label>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <label className="form-label" style={{ fontSize: 11 }}>Hora (0-23)</label>
            <input className="form-input" type="number" min={0} max={23} value={form.backup_hour} disabled={locked}
              onChange={e => setForm({ ...form, backup_hour: +e.target.value })} />
          </div>
          <div>
            <label className="form-label" style={{ fontSize: 11 }}>Minuto (0-59)</label>
            <input className="form-input" type="number" min={0} max={59} value={form.backup_minute} disabled={locked}
              onChange={e => setForm({ ...form, backup_minute: +e.target.value })} />
          </div>
        </div>
        {locked && (
          <div className="text-xs text-muted" style={{ marginTop: 6 }}>
            Definido pelo {singularMin} {customerName}. Para mudar, edite o horário na tela do {singularMin}.
          </div>
        )}
      </div>
      <div className="form-group">
        <label className="form-label">E-mails de Notificação (separados por vírgula)</label>
        <input className="form-input" value={form.email_to} disabled={emailLocked}
          onChange={e => setForm({ ...form, email_to: e.target.value })} />
        {emailLocked && (
          <div className="text-xs text-muted" style={{ marginTop: 6 }}>
            Definido pelo {singularMin} {emailCustomerName}. O relatório sai em um único e-mail por rodada do {singularMin};
            para mudar os destinatários, edite o {singularMin}.
          </div>
        )}
      </div>
      <div className="form-group">
        <label className="form-label">Nova senha do ZIP <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>(vazio = manter atual)</span></label>
        <input className="form-input" type="password" value={form.zip_password}
          onChange={e => setForm({ ...form, zip_password: e.target.value })} />
        <div className="text-xs text-muted" style={{ marginTop: 6 }}>
          Esta senha protege exclusivamente os arquivos de backup desta máquina, independente da senha do {singularMin}.
        </div>
      </div>
      <div className="flex gap-3 mt-4" style={{ justifyContent: "flex-end" }}>
        <button className="btn btn-secondary" onClick={onClose}>Cancelar</button>
        <button className="btn btn-primary" onClick={onSave} disabled={saving}>
          {saving ? <span className="spinner spinner-sm" /> : "Salvar"}
        </button>
      </div>
    </Modal>
  );
}
