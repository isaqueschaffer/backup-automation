import { useState } from "react";
import { Save } from "lucide-react";
import Modal from "../../../components/Modal";

export interface CustomerForm {
  name: string;
  description: string;
  backup_hour: number;
  backup_minute: number;
}

export const emptyCustomerForm = (): CustomerForm => ({
  name: "", description: "", backup_hour: 2, backup_minute: 0,
});

// Formulário de Cliente (criar e editar). Em edição, avisa que o horário vale para todas as máquinas.
export default function CustomerFormModal({ title, initial, isEdit, saving, onSave, onClose }: {
  title: string;
  initial: CustomerForm;
  isEdit?: boolean;
  saving: boolean;
  onSave: (form: CustomerForm) => void;
  onClose: () => void;
}) {
  const [form, setForm] = useState<CustomerForm>(initial);

  return (
    <Modal title={title} onClose={onClose}>
      <div className="form-group">
        <label className="form-label">Nome do cliente *</label>
        <input className="form-input" placeholder="Ex: Supermercado Central" value={form.name}
          onChange={e => setForm({ ...form, name: e.target.value })} />
      </div>
      <div className="form-group">
        <label className="form-label">Descrição (opcional)</label>
        <input className="form-input" placeholder="Ex: Matriz e filiais da zona sul" value={form.description}
          onChange={e => setForm({ ...form, description: e.target.value })} />
      </div>
      <div className="flex gap-3">
        <div className="form-group" style={{ flex: 1 }}>
          <label className="form-label">Hora do backup diário (BRT)</label>
          <input className="form-input" type="number" min={0} max={23} value={form.backup_hour}
            onChange={e => setForm({ ...form, backup_hour: +e.target.value })} />
        </div>
        <div className="form-group" style={{ flex: 1 }}>
          <label className="form-label">Minuto</label>
          <input className="form-input" type="number" min={0} max={59} value={form.backup_minute}
            onChange={e => setForm({ ...form, backup_minute: +e.target.value })} />
        </div>
      </div>
      <div style={{
        background: "var(--warn-bg)", border: "1px solid rgba(245,158,11,0.3)", borderRadius: "var(--radius-sm)",
        padding: "10px 14px", color: "var(--warn)", fontSize: 12,
      }}>
        {isEdit
          ? "O horário vale para todas as máquinas deste cliente. Ao alterá-lo, o agente de cada máquina é reiniciado para aplicar o novo horário."
          : "O horário vale para todas as máquinas que forem adicionadas a este cliente."}
      </div>
      <div className="flex gap-3 mt-4" style={{ justifyContent: "flex-end" }}>
        <button className="btn btn-secondary" onClick={onClose}>Cancelar</button>
        <button className="btn btn-primary" onClick={() => onSave(form)} disabled={saving}>
          {saving ? <span className="spinner spinner-sm" /> : <><Save size={15} /> Salvar</>}
        </button>
      </div>
    </Modal>
  );
}
