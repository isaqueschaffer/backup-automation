import Modal from "../../../../components/Modal";

// Campos editáveis da máquina (email_to como texto separado por vírgula).
// Cliente e posição na fila são alterados na tela do Cliente.
export interface EditMachineForm {
  name: string;
  backup_hour: number;
  backup_minute: number;
  email_to: string;
  zip_password: string;
}

export default function EditMachineModal({ form, setForm, customerName, emailCustomerName, saving, onSave, onClose }: {
  form: EditMachineForm;
  setForm: React.Dispatch<React.SetStateAction<EditMachineForm>>;
  // Nome do cliente quando o horário vem dele (campo travado); null = horário próprio
  customerName: string | null;
  // Nome do cliente quando os e-mails vêm dele (campo travado e não enviado no PUT); null = e-mails próprios
  emailCustomerName: string | null;
  saving: boolean;
  onSave: () => void;
  onClose: () => void;
}) {
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
            Definido pelo cliente {customerName}. Para mudar, edite o horário na tela do cliente.
          </div>
        )}
      </div>
      <div className="form-group">
        <label className="form-label">E-mails de Notificação (separados por vírgula)</label>
        <input className="form-input" value={form.email_to} disabled={emailLocked}
          onChange={e => setForm({ ...form, email_to: e.target.value })} />
        {emailLocked && (
          <div className="text-xs text-muted" style={{ marginTop: 6 }}>
            Definido pelo cliente {emailCustomerName}. O relatório sai em um único e-mail por rodada do cliente;
            para mudar os destinatários, edite o cliente.
          </div>
        )}
      </div>
      <div className="form-group">
        <label className="form-label">Nova senha do ZIP <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>(vazio = manter atual)</span></label>
        <input className="form-input" type="password" value={form.zip_password}
          onChange={e => setForm({ ...form, zip_password: e.target.value })} />
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
