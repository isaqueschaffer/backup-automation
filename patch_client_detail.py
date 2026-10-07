import re

def main():
    with open("server/dashboard/src/pages/ClientDetail.tsx", "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Add api to imports
    content = content.replace('import api from "../api/client";', '') # remove if exists to avoid dup
    content = content.replace('import { useToast } from "../components/Toast";', 'import { useToast } from "../components/Toast";\nimport api from "../api/client";\nimport { useRef } from "react";')

    # 2. Add CAMERA to TIPOS inside the component
    content = content.replace('const TIPOS: TipoEquipamento[] = ["NVR", "OLT", "PABX", "MIKROTIK", "DIGIFORT", "DEFENSE"];', 'const TIPOS: TipoEquipamento[] = ["NVR", "OLT", "PABX", "MIKROTIK", "DIGIFORT", "DEFENSE", "CAMERA"];')
    content = content.replace('const TIPO_ICONE_EMOJI: Record<string, string> = { NVR: "📹", OLT: "📡", PABX: "📞", MIKROTIK: "🌐", DIGIFORT: "🛡️", DEFENSE: "🛡️" };', 'const TIPO_ICONE_EMOJI: Record<string, string> = { NVR: "📹", OLT: "📡", PABX: "📞", MIKROTIK: "🌐", DIGIFORT: "🛡️", DEFENSE: "🛡️", CAMERA: "📷" };')

    # 3. Add activeTab state
    content = content.replace('const [loading, setLoading] = useState(true);', 'const [loading, setLoading] = useState(true);\n  const [activeTab, setActiveTab] = useState<"geral" | "cameras">("geral");\n  const fileInputRef = useRef<HTMLInputElement>(null);\n  const [isTesting, setIsTesting] = useState(false);\n  const [testResults, setTestResults] = useState<Record<string, {status: string, error?: string, image_base64?: string}>>({});')

    # 4. Insert the tabs UI after the banner
    tab_ui = """
      {/* TABS */}
      <div style={{ display: "flex", gap: 20, borderBottom: "1px solid var(--border)", marginBottom: 20 }}>
        <button
          style={{ padding: "10px 16px", cursor: "pointer", borderBottom: activeTab === "geral" ? "2px solid var(--primary)" : "none", color: activeTab === "geral" ? "var(--primary)" : "var(--text-muted)", fontWeight: 600, background: "transparent", borderTop: "none", borderLeft: "none", borderRight: "none", fontSize: 14 }}
          onClick={() => setActiveTab("geral")}
        >
          Visão Geral & Equipamentos
        </button>
        <button
          style={{ padding: "10px 16px", cursor: "pointer", borderBottom: activeTab === "cameras" ? "2px solid var(--primary)" : "none", color: activeTab === "cameras" ? "var(--primary)" : "var(--text-muted)", fontWeight: 600, background: "transparent", borderTop: "none", borderLeft: "none", borderRight: "none", fontSize: 14 }}
          onClick={() => setActiveTab("cameras")}
        >
          Câmeras / Teste RTSP
        </button>
      </div>

      {activeTab === "geral" && (
        <>
"""
    # Replace the start of the Layout de duas colunas with the Tab UI + open fragment
    content = content.replace('{/* 🗂️ Layout de duas colunas 🗂️ */}', tab_ui + '      {/* 🗂️ Layout de duas colunas 🗂️ */}')

    # 5. Close the fragment at the end of "geral" tab content and add the "cameras" tab content
    end_of_geral = "{/* 🛠️ Modal: Adicionar Equipamento 🛠️ */}"
    
    cameras_tab = """
        </>
      )}

      {activeTab === "cameras" && (
        <div style={{ marginBottom: 24 }}>
          <div className="flex items-center justify-between mb-4">
            <div className="section-title mb-0">
              <Video size={15} /> Câmeras do Cliente
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
                  <th style={{ padding: '12px 16px' }}>Ações</th>
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
                      <td style={{ padding: '12px 16px' }}>
                        <button onClick={() => handleDeleteEquipamento(cam.id, cam.name)} disabled={isTesting} style={{ background: 'none', border: 'none', color: '#dc2626', cursor: 'pointer' }}>Remover</button>
                      </td>
                    </tr>
                  );
                })}
                {equipamentos.filter(e => e.tipo === "CAMERA").length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', padding: 30, color: 'var(--text-muted)' }}>Nenhuma câmera cadastrada para este cliente.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

"""
    content = content.replace(end_of_geral, cameras_tab + end_of_geral)

    with open("server/dashboard/src/pages/ClientDetail.tsx", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    main()
