import { useState } from "react";
import { Plus } from "lucide-react";
import { Customer } from "../../../api/types";
import Modal from "../../../components/Modal";
import { fmtSchedule } from "../../../utils/date";

export interface NewMachineForm {
  name: string;
  customer_id: string; // "" = sem cliente
  backup_hour: number;
  backup_minute: number;
  email_to: string;
  zip_password: string;
}

export default function NewMachineModal({ customers, initialCustomerId, saving, onSave, onClose }: {
  customers: Customer[];
  initialCustomerId?: string;
  saving: boolean;
  onSave: (form: NewMachineForm) => void;
  onClose: () => void;
}) {
  const [form, setForm] = useState<NewMachineForm>({
    name: "", customer_id: initialCustomerId || "", backup_hour: 2, backup_minute: 0, email_to: "", zip_password: "",
  });
  const customer = customers.find(c => c.id === form.customer_id);

  return (
    <Modal title="Nova Máquina" onClose={onClose}>
      <div className="form-group">
        <label className="form-label">Nome da máquina *</label>
        <input className="form-input" placeholder="Ex: Servidor Loja Centro" value={form.name}
          onChange={e => setForm({ ...form, name: e.target.value })} />
      </div>
      <div className="form-group">
        <label className="form-label">Cliente (opcional)</label>
        <select className="form-input" value={form.customer_id}
          onChange={e => setForm({ ...form, customer_id: e.target.value })}>
          <option value="">Sem cliente</option>
          {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>
      {customer ? (
        <div className="form-group">
          <label className="form-label">Horário do backup</label>
          <input className="form-input" disabled value={`${fmtSchedule(customer.backup_hour, customer.backup_minute)} — definido pelo cliente ${customer.name}`} />
          <div className="text-xs text-muted" style={{ marginTop: 4 }}>
            Máquinas de um cliente herdam o horário dele e entram no fim da fila de backup do cliente.
          </div>
        </div>
      ) : (
        <div className="flex gap-3">
          <div className="form-group" style={{ flex: 1 }}>
            <label className="form-label">Hora do backup</label>
            <input className="form-input" type="number" min={0} max={23} value={form.backup_hour}
              onChange={e => setForm({ ...form, backup_hour: +e.target.value })} />
          </div>
          <div className="form-group" style={{ flex: 1 }}>
            <label className="form-label">Minuto</label>
            <input className="form-input" type="number" min={0} max={59} value={form.backup_minute}
              onChange={e => setForm({ ...form, backup_minute: +e.target.value })} />
          </div>
        </div>
      )}
      <div className="form-group">
        <label className="form-label">Destinatários de e-mail (separados por vírgula)</label>
        <input className="form-input" placeholder="ti@empresa.com, gestor@empresa.com"
          value={form.email_to} onChange={e => setForm({ ...form, email_to: e.target.value })} />
      </div>
      <div className="form-group">
        <label className="form-label">Senha do ZIP (opcional — gerada automaticamente se vazio)</label>
        <input className="form-input" type="password" placeholder="SenhaForte123"
          value={form.zip_password} onChange={e => setForm({ ...form, zip_password: e.target.value })} />
      </div>
      <div className="flex gap-3 mt-4" style={{ justifyContent: "flex-end" }}>
        <button className="btn btn-secondary" onClick={onClose}>Cancelar</button>
        <button className="btn btn-primary" onClick={() => onSave(form)} disabled={saving}>
          {saving ? <span className="spinner spinner-sm" /> : <><Plus size={15} /> Criar</>}
        </button>
      </div>
    </Modal>
  );
}
