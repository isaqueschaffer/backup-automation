import { ClientGroup } from "../../../api/types";
import Modal from "../../../components/Modal";

// Campos editáveis da máquina (email_to como texto separado por vírgula)
export interface EditClientForm {
  name: string;
  backup_hour: number;
  backup_minute: number;
  group_id: string;
  queue_order: number;
  email_to: string;
  zip_password: string;
}

export default function EditClientModal({ form, setForm, groups, saving, onSave, onClose }: {
  form: EditClientForm;
  setForm: React.Dispatch<React.SetStateAction<EditClientForm>>;
  groups: ClientGroup[];
  saving: boolean;
  onSave: () => void;
  onClose: () => void;
}) {
  return (
    <Modal title="Editar Cliente" onClose={onClose}>
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
            <input className="form-input" type="number" min={0} max={23} value={form.backup_hour}
              onChange={e => setForm({ ...form, backup_hour: +e.target.value })} />
          </div>
          <div>
            <label className="form-label" style={{ fontSize: 11 }}>Minuto (0-59)</label>
            <input className="form-input" type="number" min={0} max={59} value={form.backup_minute}
              onChange={e => setForm({ ...form, backup_minute: +e.target.value })} />
          </div>
        </div>
      </div>
      <div className="form-group">
        <label className="form-label">Unidade (opcional)</label>
        <select className="form-input"
          value={form.group_id}
          onChange={e => setForm({ ...form, group_id: e.target.value })}>
          <option value="">— Sem unidade —</option>
          {groups.map(g => (
            <option key={g.id} value={g.id}>{g.name}</option>
          ))}
        </select>
      </div>
      {form.group_id && (
        <div className="form-group">
          <label className="form-label">Ordem na fila de backup da unidade (0, 1, 2...)</label>
          <input className="form-input" type="number" min={0}
            value={form.queue_order}
            onChange={e => setForm({ ...form, queue_order: +e.target.value })} />
        </div>
      )}
      <div className="form-group">
        <label className="form-label">E-mails de Notificação (separados por vírgula)</label>
        <input className="form-input" value={form.email_to}
          onChange={e => setForm({ ...form, email_to: e.target.value })} />
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
