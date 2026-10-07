import React, { useState, useRef } from "react";
import api from "../api/client";
import { useToast } from "../components/Toast";

interface Camera {
  id: string;
  nome: string;
  ip: string;
  modelo: string;
  senha?: string;
  status: "idle" | "testing" | "success" | "error";
  error_message?: string;
  image_base64?: string;
}

export default function RTSPTest() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [isTesting, setIsTesting] = useState(false);
  const { showToast } = useToast();
  
  // Inputs manuais
  const [nome, setNome] = useState("");
  const [ip, setIp] = useState("");
  const [modelo, setModelo] = useState("Hikvision");
  const [senha, setSenha] = useState("");

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleAddCamera = (e: React.FormEvent) => {
    e.preventDefault();
    if (!nome || !ip) return;
    setCameras(prev => [...prev, {
      id: Math.random().toString(36).substr(2, 9),
      nome, ip, modelo, senha, status: "idle"
    }]);
    setNome(""); setIp(""); setSenha("");
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (evt) => {
      const text = evt.target?.result as string;
      const lines = text.split("\n");
      const newCams: Camera[] = [];
      
      for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;
        const cols = line.split(";").map(c => c.replace(/^"|"$/g, "").trim());
        
        // Padrão do CSV do usuário:
        // "Nome";"Descrição";"Modelo";"Endereço";"Diretório de gravação";"Arquivamento";"Senha"
        const desc = cols[1] || "";
        const mod = cols[2] || "Hikvision";
        const ender = cols[3] || "";
        const pass = cols[6] || "";

        if (desc && ender) {
          newCams.push({
            id: Math.random().toString(36).substr(2, 9),
            nome: desc,
            ip: ender,
            modelo: mod,
            senha: pass,
            status: "idle"
          });
        }
      }

      if (newCams.length > 0) {
        setCameras(prev => [...prev, ...newCams]);
        showToast(`Importadas ${newCams.length} câmeras com sucesso!`, "success");
      }
      
      // Reseta o input
      if (fileInputRef.current) fileInputRef.current.value = '';
    };
    // Lê como ISO-8859-1 para garantir que caracteres acentuados funcionem
    reader.readAsText(file, "ISO-8859-1"); 
  };

  const handleTestAll = async () => {
    if (cameras.length === 0) return;
    setIsTesting(true);

    for (let i = 0; i < cameras.length; i++) {
      const cam = cameras[i];
      if (cam.status === "success") continue; // Pula as que já estão OK

      // Marca como testando
      setCameras(prev => prev.map(c => c.id === cam.id ? { ...c, status: "testing", error_message: undefined } : c));

      try {
        const res = await api.post("/rtsp/test-single", {
          nome: cam.nome,
          ip: cam.ip,
          modelo: cam.modelo,
          senha: cam.senha || "navarro@123"
        });

        if (res.data.success) {
          setCameras(prev => prev.map(c => c.id === cam.id ? { ...c, status: "success", image_base64: res.data.image_base64 } : c));
        } else {
          setCameras(prev => prev.map(c => c.id === cam.id ? { ...c, status: "error", error_message: res.data.error_message } : c));
        }
      } catch (err: any) {
        setCameras(prev => prev.map(c => c.id === cam.id ? { ...c, status: "error", error_message: "Erro de comunicação na API (timeout ou erro de rede)." } : c));
      }
    }
    
    setIsTesting(false);
    showToast("Teste de RTSP concluído!", "success");
  };

  const removerCamera = (id: string) => {
    setCameras(prev => prev.filter(c => c.id !== id));
  };

  const limparLista = () => {
    setCameras([]);
  };

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2>Testador RTSP Automático</h2>
        <div style={{ display: 'flex', gap: 10 }}>
          <input type="file" accept=".csv" ref={fileInputRef} style={{ display: 'none' }} onChange={handleFileUpload} />
          <button className="btn btn-secondary" onClick={() => fileInputRef.current?.click()} disabled={isTesting}>
            Importar CSV
          </button>
          <button className="btn btn-danger" onClick={limparLista} disabled={isTesting}>Limpar</button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 20, padding: 20, border: '1px solid #ddd', borderRadius: 8 }}>
        <h4>Adicionar Manualmente</h4>
        <form onSubmit={handleAddCamera} style={{ display: 'flex', gap: 10, alignItems: 'flex-end', marginTop: 15 }}>
          <div style={{ flex: 1 }}>
            <label>Descrição</label>
            <input type="text" className="form-control" value={nome} onChange={e => setNome(e.target.value)} required />
          </div>
          <div style={{ flex: 1 }}>
            <label>IP</label>
            <input type="text" className="form-control" value={ip} onChange={e => setIp(e.target.value)} required />
          </div>
          <div style={{ flex: 1 }}>
            <label>Modelo</label>
            <select className="form-control" value={modelo} onChange={e => setModelo(e.target.value)}>
              <option value="Hikvision">Hikvision / Outro</option>
              <option value="Intelbras">Intelbras</option>
              <option value="Grandstream">Grandstream</option>
              <option value="ONVIF">ONVIF Genérico</option>
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label>Senha</label>
            <input type="text" className="form-control" placeholder="navarro@123" value={senha} onChange={e => setSenha(e.target.value)} />
          </div>
          <div>
            <button type="submit" className="btn btn-primary" disabled={isTesting}>Adicionar</button>
          </div>
        </form>
      </div>

      <div className="card" style={{ padding: 20, border: '1px solid #ddd', borderRadius: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 15 }}>
          <h4>Fila de Teste ({cameras.length})</h4>
          <button className="btn btn-success" onClick={handleTestAll} disabled={isTesting || cameras.length === 0}>
            {isTesting ? "Testando..." : "Iniciar Teste RTSP"}
          </button>
        </div>
        
        <table className="table" style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #ccc', textAlign: 'left' }}>
              <th>Descrição</th>
              <th>IP</th>
              <th>Modelo</th>
              <th>Status</th>
              <th>Preview</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            {cameras.map(cam => (
              <tr key={cam.id} style={{ borderBottom: '1px solid #eee' }}>
                <td style={{ padding: '10px 0' }}>{cam.nome}</td>
                <td>{cam.ip}</td>
                <td>{cam.modelo}</td>
                <td>
                  {cam.status === "idle" && <span style={{ color: '#888' }}>⏳ Aguardando</span>}
                  {cam.status === "testing" && <span style={{ color: '#d97706' }}>🔄 Testando...</span>}
                  {cam.status === "success" && <span style={{ color: '#16a34a', fontWeight: 'bold' }}>✅ Sucesso</span>}
                  {cam.status === "error" && (
                    <div>
                      <span style={{ color: '#dc2626', fontWeight: 'bold' }}>❌ Erro</span>
                      <div style={{ fontSize: '0.8rem', color: '#dc2626', marginTop: 4 }}>{cam.error_message}</div>
                    </div>
                  )}
                </td>
                <td>
                  {cam.image_base64 && (
                    <img src={`data:image/jpeg;base64,${cam.image_base64}`} alt="Preview" style={{ maxHeight: '60px', borderRadius: '4px', border: '1px solid #ccc' }} />
                  )}
                </td>
                <td>
                  <button onClick={() => removerCamera(cam.id)} disabled={isTesting} style={{ background: 'none', border: 'none', color: '#dc2626', cursor: 'pointer' }}>Remover</button>
                </td>
              </tr>
            ))}
            {cameras.length === 0 && (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', padding: 20, color: '#888' }}>Lista vazia.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
