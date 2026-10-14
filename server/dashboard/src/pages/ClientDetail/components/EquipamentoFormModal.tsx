import { Plus } from "lucide-react";
import { EqForm, TipoEquipamento } from "../../../api/types";
import Modal from "../../../components/Modal";
import { TIPOS, TIPO_ICONE_EMOJI } from "../utils";

export default function EquipamentoFormModal({ eqForm, setEqForm, editingEqId, saving, onSave, onClose }: {
  eqForm: EqForm;
  setEqForm: React.Dispatch<React.SetStateAction<EqForm>>;
  editingEqId: string | null;
  saving: boolean;
  onSave: () => void;
  onClose: () => void;
}) {
  const isSshOlt = eqForm.fabricante_olt === "VSOL" || eqForm.fabricante_olt === "HUAWEI";

  return (
    <Modal title={editingEqId ? "Editar Equipamento" : "Adicionar Equipamento"} onClose={onClose}>
      <div className="form-group">
        <label className="form-label">Tipo de Equipamento *</label>
        {eqForm.tipo === "CAMERA" ? (
          <div style={{ padding: "10px", background: "rgba(255,255,255,0.05)", borderRadius: 6, marginBottom: 16 }}>📷 Câmera (RTSP)</div>
        ) : (
        <select className="form-input" value={eqForm.tipo}
          onChange={e => setEqForm({ ...eqForm, tipo: e.target.value as TipoEquipamento, pasta_origem: e.target.value === "DEFENSE" ? "C:\\Intelbras Defense IA\\Intelbras Defense IA Server\\bak\\db_backup" : "", fabricante_olt: "UNM2000" })}>
          {TIPOS.map(t => <option key={t} value={t}>{TIPO_ICONE_EMOJI[t]} {t}</option>)}
        </select>
        )}
      </div>
      <div className="form-group">
        <label className="form-label">Nome *</label>
        <input className="form-input" type="text"
          placeholder={`${eqForm.tipo}_Cliente1`}
          value={eqForm.name} onChange={e => setEqForm({ ...eqForm, name: e.target.value })} />
      </div>
      {(eqForm.tipo === "NVR" || eqForm.tipo === "PABX" || eqForm.tipo === "MIKROTIK" || eqForm.tipo === "CAMERA") && (
        <>
          <div className="form-group">
            <label className="form-label">Endereço IP ou Host *</label>
            <input className="form-input" type="text" placeholder={eqForm.tipo === "PABX" ? "https://192.168.12.2" : "192.168.1.100"}
              value={eqForm.ip} onChange={e => setEqForm({ ...eqForm, ip: e.target.value })} />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label">Usuário *</label>
              <input className="form-input" type="text"
                value={eqForm.username} onChange={e => setEqForm({ ...eqForm, username: e.target.value })} />
            </div>
            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label">Senha {editingEqId ? <span style={{fontWeight:400, color:'var(--text-muted)'}}>(vazio = manter atual)</span> : '*'}</label>
              <input className="form-input" type="password"
                value={eqForm.password} onChange={e => setEqForm({ ...eqForm, password: e.target.value })} />
            </div>
          </div>
          {eqForm.tipo === "CAMERA" && (
            <div className="form-group" style={{ marginTop: 12 }}>
              <label className="form-label">Modelo / Fabricante</label>
              <select className="form-input" value={eqForm.modelo || "Hikvision"} onChange={e => setEqForm({ ...eqForm, modelo: e.target.value })}>
                <option value="Hikvision">Hikvision / Outro</option>
                <option value="Intelbras">Intelbras</option>
                <option value="Grandstream">Grandstream</option>
                <option value="ONVIF">ONVIF Genérico</option>
              </select>
            </div>
          )}
          {eqForm.tipo === "NVR" && (
            <div className="form-group" style={{ marginTop: 12 }}>
              <label className="form-label">Marca do NVR</label>
              <select className="form-input" value={eqForm.marca || "Hikvision"} onChange={e => setEqForm({ ...eqForm, marca: e.target.value })}>
                <option value="Hikvision">Hikvision / Intelbras / Outros</option>
                <option value="Motorola">Motorola</option>
              </select>
            </div>
          )}
        </>
      )}
      {eqForm.tipo === "OLT" && (
        <>
          <div className="form-group">
            <label className="form-label">Sistema da OLT *</label>
            <select
              className="form-input"
              value={eqForm.fabricante_olt}
              onChange={e => setEqForm({ ...eqForm, fabricante_olt: e.target.value })}
            >
              <option value="UNM2000">🔵 UNM2000</option>
              <option value="HUAWEI">🔴 HUAWEI</option>
              <option value="VSOL">🟢 VSOL</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">
              {isSshOlt ? "Endereço IP da OLT *" : "Pasta de Origem dos Backups *"}
            </label>

            <input
              className="form-input"
              type="text"
              placeholder={isSshOlt ? "192.168.1.100" : "C:\\Users\\Helena\\Documents"}
              value={isSshOlt ? eqForm.ip : eqForm.pasta_origem}
              onChange={e => {
                if (isSshOlt) {
                  setEqForm({ ...eqForm, ip: e.target.value });
                } else {
                  setEqForm({ ...eqForm, pasta_origem: e.target.value });
                }
              }}
            />
          </div>

          {isSshOlt && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
              <div className="form-group" style={{ margin: 0 }}>
                <label className="form-label">Usuário *</label>
                <input
                  className="form-input"
                  type="text"
                  value={eqForm.username}
                  onChange={e => setEqForm({ ...eqForm, username: e.target.value })}
                />
              </div>

              <div className="form-group" style={{ margin: 0 }}>
                <label className="form-label">Senha *</label>
                <input
                  className="form-input"
                  type="password"
                  value={eqForm.password}
                  onChange={e => setEqForm({ ...eqForm, password: e.target.value })}
                />
              </div>
            </div>
          )}

          <span style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, display: "block" }}>
            {(eqForm.fabricante_olt === "UNM2000")
              ? `Pasta onde o ${eqForm.fabricante_olt} exporta os arquivos de backup.`
              : "Endereço IP, usuário e senha utilizados para acessar a OLT via SSH."
            }
          </span>
        </>
      )}
      {eqForm.tipo === "DIGIFORT" && (
        <>
          <div className="form-group">
            <label className="form-label">Pasta de Origem do Digifort *</label>
            <input className="form-input" type="text"
              placeholder="C:\Digifort\Backup"
              value={eqForm.pasta_origem} onChange={e => setEqForm({ ...eqForm, pasta_origem: e.target.value })} />
          </div>
          <div className="form-group">
            <label className="form-label">Caminho do CSV Exportado (Opcional)</label>
            <input className="form-input" type="text"
              placeholder="export_cameras.csv"
              value={eqForm.caminho_csv || ""} onChange={e => setEqForm({ ...eqForm, caminho_csv: e.target.value })} />
            <span style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, display: "block" }}>
              Arquivo CSV com a descrição das câmeras gerado pelo Digifort.
            </span>
          </div>
          <div className="form-group">
            <label className="form-label">Caminho do LOG de Gravações (Opcional)</label>
            <input className="form-input" type="text"
              placeholder="C:\...\quedas_cameras.csv"
              value={eqForm.caminho_log_csv || ""} onChange={e => setEqForm({ ...eqForm, caminho_log_csv: e.target.value })} />
            <span style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, display: "block" }}>
              Arquivo CSV onde o Agente Webhook salva/lê o histórico (quedas_cameras.csv).
            </span>
          </div>
        </>
      )}
      {eqForm.tipo === "DEFENSE" && (
        <div className="form-group">
          <label className="form-label">Pasta de Origem do Backup *</label>
          <input className="form-input" type="text"
            placeholder="C:\Intelbras Defense IA\...\db_backup"
            value={eqForm.pasta_origem} onChange={e => setEqForm({ ...eqForm, pasta_origem: e.target.value })} />
          <span style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, display: "block" }}>
            Pasta onde o Defense IA salva os arquivos gerados no backup automático.
          </span>
        </div>
      )}
      <div className="flex gap-3 mt-4" style={{ justifyContent: "flex-end" }}>
        <button className="btn btn-secondary" onClick={onClose}>Cancelar</button>
        <button className="btn btn-primary" onClick={onSave} disabled={saving}>
          {saving ? <span className="spinner spinner-sm" /> : (editingEqId ? "Salvar" : <><Plus size={15} /> Adicionar</>)}
        </button>
      </div>
    </Modal>
  );
}
