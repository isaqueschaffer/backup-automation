import sys

def main():
    path = "server/dashboard/src/pages/ClientDetail.tsx"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Imports
    if 'import api from "../api/client";' not in content:
        content = content.replace('import { useToast } from "../components/Toast";', 
                                  'import { useToast } from "../components/Toast";\nimport api from "../api/client";\nimport { useRef } from "react";\nimport { Video } from "lucide-react";')

    # 2. State
    state_injection = """
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isTesting, setIsTesting] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, {status: string, error?: string, image_base64?: string}>>({});
"""
    if 'const fileInputRef' not in content:
        content = content.replace('const [loading, setLoading] = useState(true);', 
                                  'const [loading, setLoading] = useState(true);\n' + state_injection)

    # 3. EqPayload update for CAMERA
    # Find buildEqPayload
    content = content.replace('if (eqForm.tipo === "NVR" || eqForm.tipo === "PABX" || eqForm.tipo === "MIKROTIK") {',
                              'if (eqForm.tipo === "NVR" || eqForm.tipo === "PABX" || eqForm.tipo === "MIKROTIK" || eqForm.tipo === "CAMERA") {\n      if (eqForm.tipo === "CAMERA") payload.config_extra = { modelo: (eqForm as any).modelo || "Hikvision" };')

    # 4. Filter generic equipamentos section
    content = content.replace('{equipamentos.length}', '{equipamentos.filter(e => e.tipo !== "CAMERA").length}')
    content = content.replace('{equipamentos.length === 0 ? (', '{equipamentos.filter(e => e.tipo !== "CAMERA").length === 0 ? (')
    content = content.replace('{equipamentos.map(eq => (', '{equipamentos.filter(e => e.tipo !== "CAMERA").map(eq => (')

    # 5. Add Cǽmeras section right after Equipamentos (before Histrico de Eventos do Agente)
    cameras_section = """
      {/*  Cmeras (Teste RTSP)  */}
      <div style={{ marginBottom: 24, marginTop: 24 }}>
        <div className="flex items-center justify-between mb-4">
          <div className="section-title mb-0">
            <Video size={15} /> Câmeras do Cliente (Teste RTSP)
            <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}>
              {equipamentos.filter(e => e.tipo === "CAMERA").length}
            </span>
          </div>
          <div className="flex gap-2">
            <input type="file" accept=".csv" ref={fileInputRef} style={{ display: 'none' }} onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              const reader = new FileReader();
              reader.onload = async (evt) => {
                const text = evt.target?.result as string;
                const lines = text.split("\\n");
                let count = 0;
                setLoading(true);
                try {
                  for (let i = 1; i < lines.length; i++) {
                    const line = lines[i].trim();
                    if (!line) continue;
                    const cols = line.split(";").map(c => c.replace(/^"|"$/g, "").trim());
                    const desc = cols[1] || "";
                    const mod = cols[2] || "Hikvision";
                    const ender = cols[3] || "";
                    const pass = cols[6] || "";

                    if (desc && ender) {
                      await createEquipamento(id!, {
                        tipo: "CAMERA",
                        name: desc,
                        ip: ender,
                        username: "admin",
                        password: pass,
                        config_extra: { modelo: mod }
                      });
                      count++;
                    }
                  }
                  toast(`Importadas ${count} câmeras com sucesso!`, "success");
                  load();
                } catch (err) {
                  toast("Erro ao importar câmeras.", "error");
                } finally {
                  setLoading(false);
                  if (fileInputRef.current) fileInputRef.current.value = '';
                }
              };
              reader.readAsText(file, "ISO-8859-1");
            }} />
            <button className="btn btn-secondary" onClick={() => fileInputRef.current?.click()} disabled={loading || isTesting}>
              <Plus size={14} /> Importar CSV
            </button>
            <button className="btn btn-secondary" onClick={() => { setEditingEqId(null); setEqForm({ tipo: "CAMERA", name: "", ip: "", username: "admin", password: "navarro@123", modelo: "Hikvision" } as any); setShowEqModal(true); }}>
              <Plus size={14} /> Adicionar Câmera
            </button>
            <button className="btn btn-success" disabled={loading || isTesting || equipamentos.filter(e => e.tipo === "CAMERA").length === 0} onClick={async () => {
              const cams = equipamentos.filter(e => e.tipo === "CAMERA");
              if (cams.length === 0) return;
              setIsTesting(true);
              setTestResults({});
              
              for (const cam of cams) {
                setTestResults(prev => ({ ...prev, [cam.id]: { status: "testing" } }));
                try {
                  const res = await api.post(`/clients/${id}/equipamentos/${cam.id}/test-rtsp`);
                  if (res.data.success) {
                    setTestResults(prev => ({ ...prev, [cam.id]: { status: "success", image_base64: res.data.image_base64 } }));
                  } else {
                    setTestResults(prev => ({ ...prev, [cam.id]: { status: "error", error: res.data.error_message } }));
                  }
                } catch (err: any) {
                  setTestResults(prev => ({ ...prev, [cam.id]: { status: "error", error: "Erro de comunicação na API." } }));
                }
              }
              setIsTesting(false);
              toast("Teste RTSP concluído!", "success");
            }}>
              {isTesting ? "Testando..." : "Testar Todas"}
            </button>
          </div>
        </div>

        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="table" style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--border)', textAlign: 'left', background: 'var(--surface-2)' }}>
                <th style={{ padding: '12px 16px' }}>Descrição</th>
                <th style={{ padding: '12px 16px' }}>IP</th>
                <th style={{ padding: '12px 16px' }}>Modelo</th>
                <th style={{ padding: '12px 16px' }}>Status RTSP</th>
                <th style={{ padding: '12px 16px' }}>Preview</th>
                <th style={{ padding: '12px 16px', textAlign: 'right' }}>Ações</th>
              </tr>
            </thead>
            <tbody>
              {equipamentos.filter(e => e.tipo === "CAMERA").map(cam => {
                const res = testResults[cam.id];
                return (
                  <tr key={cam.id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '12px 16px' }}>{cam.name}</td>
                    <td style={{ padding: '12px 16px', fontFamily: 'monospace' }}>{cam.ip}</td>
                    <td style={{ padding: '12px 16px' }}>{(cam.config_extra as any)?.modelo || "N/A"}</td>
                    <td style={{ padding: '12px 16px' }}>
                      {!res && <span style={{ color: '#888' }}>⏳ Aguardando</span>}
                      {res?.status === "testing" && <span style={{ color: '#d97706' }}>🔄 Testando...</span>}
                      {res?.status === "success" && <span style={{ color: '#16a34a', fontWeight: 'bold' }}>✅ Sucesso</span>}
                      {res?.status === "error" && (
                        <div>
                          <span style={{ color: '#dc2626', fontWeight: 'bold' }}>❌ Erro</span>
                          <div style={{ fontSize: '0.8rem', color: '#dc2626', marginTop: 4 }}>{res.error}</div>
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      {res?.image_base64 && (
                        <img src={`data:image/jpeg;base64,${res.image_base64}`} alt="Preview" style={{ maxHeight: '60px', borderRadius: '4px', border: '1px solid #ccc' }} />
                      )}
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                      <button className="btn btn-secondary" style={{ padding: '4px 8px', fontSize: 12, marginRight: 8 }} onClick={() => {
                        setEditingEqId(cam.id);
                        setEqForm({
                          tipo: "CAMERA",
                          name: cam.name,
                          ip: cam.ip,
                          username: cam.username,
                          password: "",
                          modelo: (cam.config_extra as any)?.modelo || "Hikvision"
                        } as any);
                        setShowEqModal(true);
                      }}>Editar</button>
                      <button onClick={() => handleDeleteEquipamento(cam.id, cam.name)} disabled={isTesting} style={{ background: 'none', border: 'none', color: '#dc2626', cursor: 'pointer', fontSize: 12 }}>Remover</button>
                    </td>
                  </tr>
                );
              })}
              {equipamentos.filter(e => e.tipo === "CAMERA").length === 0 && (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: 30, color: 'var(--text-muted)' }}>Nenhuma câmera cadastrada. Use "Importar CSV" ou adicione manualmente.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
"""
    content = content.replace('{/* ── Histórico de Eventos do Agente ── */}', cameras_section + '\n      {/* ── Histórico de Eventos do Agente ── */}')

    # 6. EqModal logic
    content = content.replace(
        '<label className="form-label">Tipo de Equipamento *</label>',
        """<label className="form-label">Tipo de Equipamento *</label>
            {eqForm.tipo === "CAMERA" ? (
              <div style={{ padding: "10px", background: "rgba(255,255,255,0.05)", borderRadius: 6, marginBottom: 16 }}>📷 Câmera RTSP</div>
            ) : ("""
    )
    content = content.replace(
        '{TIPOS.map(t => <option key={t} value={t}>{TIPO_ICONE_EMOJI[t]} {t}</option>)}',
        '{TIPOS.map(t => <option key={t} value={t}>{TIPO_ICONE_EMOJI[t]} {t}</option>)}'
    )
    content = content.replace(
        '</select>\n          </div>',
        '</select>\n            )}\n          </div>'
    )

    content = content.replace(
        '{(eqForm.tipo === "NVR" || eqForm.tipo === "PABX" || eqForm.tipo === "MIKROTIK") && (',
        '{(eqForm.tipo === "NVR" || eqForm.tipo === "PABX" || eqForm.tipo === "MIKROTIK" || eqForm.tipo === "CAMERA") && ('
    )

    modelo_field = """
              {eqForm.tipo === "CAMERA" && (
                <div className="form-group" style={{ marginTop: 12 }}>
                  <label className="form-label">Modelo / Fabricante</label>
                  <select className="form-input" value={(eqForm as any).modelo || "Hikvision"} onChange={e => setEqForm({ ...eqForm, modelo: e.target.value } as any)}>
                    <option value="Hikvision">Hikvision / Outro</option>
                    <option value="Intelbras">Intelbras</option>
                    <option value="Grandstream">Grandstream</option>
                    <option value="ONVIF">ONVIF Genérico</option>
                  </select>
                </div>
              )}
"""
    content = content.replace(
        '</div>\n              </div>\n            </>',
        '</div>\n              </div>\n' + modelo_field + '            </>'
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    main()
