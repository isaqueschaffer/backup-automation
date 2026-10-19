import { useState } from "react";
import { Save, Eye, EyeOff } from "lucide-react";
import Modal from "../../../components/Modal";

export interface CustomerForm {
  name: string;
  description: string;
  backup_hour: number;
  backup_minute: number;
  // E-mails do relatório como texto separado por vírgula (vira lista ao salvar)
  email_to: string;
  password_mode: "default" | "custom";
  zip_password?: string;
  has_zip_password?: boolean;
}

export const emptyCustomerForm = (): CustomerForm => ({
  name: "", description: "", backup_hour: 2, backup_minute: 0, email_to: "", password_mode: "default", zip_password: "",
});

// "a@x.com, , b@y.com" → ["a@x.com", "b@y.com"] (trim, sem vazios, sem repetidos)
export const parseEmailList = (s: string): string[] =>
  Array.from(new Set(s.split(",").map(e => e.trim()).filter(Boolean)));

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
  const [showPassword, setShowPassword] = useState(false);

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
      <div className="form-group">
        <label className="form-label">E-mails do relatório (separados por vírgula)</label>
        <input className="form-input" placeholder="Ex: ti@cliente.com.br, gerente@cliente.com.br" value={form.email_to}
          onChange={e => setForm({ ...form, email_to: e.target.value })} />
        <div className="text-xs text-muted" style={{ marginTop: 6 }}>
          Um único e-mail por rodada com o relatório de todas as máquinas. Substitui os e-mails próprios das máquinas deste cliente.
        </div>
      </div>
      <div className="form-group">
        <label className="form-label">Senha do ZIP do cliente</label>
        <div style={{ display: "flex", gap: 20, marginTop: 6, marginBottom: 12 }}>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 13, color: "var(--text-primary)" }}>
            <input
              type="radio"
              name="password_mode"
              checked={form.password_mode === "default"}
              onChange={() => setForm({ ...form, password_mode: "default", zip_password: "" })}
            />
            <span>Usar padrão <span className="text-muted">(sem senha personalizada)</span></span>
          </label>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 13, color: "var(--text-primary)" }}>
            <input
              type="radio"
              name="password_mode"
              checked={form.password_mode === "custom"}
              onChange={() => setForm({ ...form, password_mode: "custom" })}
            />
            <span>Criar senha personalizada</span>
          </label>
        </div>

        {form.password_mode === "custom" ? (
          <div>
            <div style={{ position: "relative" }}>
              <input
                className="form-input"
                type={showPassword ? "text" : "password"}
                placeholder={isEdit && form.has_zip_password ? "•••••••• (senha já configurada — vazio para manter)" : "Digite a senha para o ZIP do cliente"}
                value={form.zip_password || ""}
                onChange={e => setForm({ ...form, zip_password: e.target.value })}
                style={{ paddingRight: 40 }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  position: "absolute",
                  right: 10,
                  top: "50%",
                  transform: "translateY(-50%)",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--text-muted)",
                  padding: 4,
                  display: "flex",
                  alignItems: "center",
                }}
                title={showPassword ? "Ocultar senha" : "Ver senha"}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <div className="text-xs text-muted" style={{ marginTop: 6 }}>
              {isEdit && form.has_zip_password && !form.zip_password
                ? "O cliente já possui senha personalizada. Deixe em branco para manter a senha atual ou digite uma nova para alterar."
                : "Esta senha protegerá exclusivamente o ZIP consolidado do cliente. As máquinas mantêm suas senhas individuais separadas (dentro deste ZIP, as pastas internas das máquinas ficam acessíveis sem senha)."}
            </div>
          </div>
        ) : (
          <div className="text-xs text-muted" style={{ background: "var(--surface)", padding: "8px 12px", borderRadius: 4, border: "1px solid var(--border)" }}>
            O ZIP deste cliente usará o padrão (sem senha personalizada no cliente).
          </div>
        )}
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
