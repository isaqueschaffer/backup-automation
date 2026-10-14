import { Plus, Trash2, Video } from "lucide-react";
import { NVR } from "../../../../api/types";
import { RtspResult } from "../hooks/useRtspTest";
import { safeFileName } from "../utils";

export default function CamerasSection({
  cameras, testResults, isTesting, loading, hasImages, fileInputRef,
  onImportFile, onImportClick, onDeleteAll, onAdd, onEdit, onRemove, onDownloadImages, onTestAll,
}: {
  cameras: NVR[];
  testResults: Record<string, RtspResult>;
  isTesting: boolean;
  loading: boolean;
  hasImages: boolean;
  fileInputRef: React.RefObject<HTMLInputElement>;
  onImportFile: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onImportClick: () => void;
  onDeleteAll: () => void;
  onAdd: () => void;
  onEdit: (cam: NVR) => void;
  onRemove: (cam: NVR) => void;
  onDownloadImages: () => void;
  onTestAll: () => void;
}) {
  return (
    <div style={{ marginBottom: 24, marginTop: 24 }}>
      <div className="flex items-center justify-between mb-4">
        <div className="section-title mb-0">
          <Video size={15} /> Câmeras da Máquina (Teste RTSP)
          <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}>
            {cameras.length}
          </span>
        </div>
        <div className="flex gap-2">
          <input type="file" accept=".csv,.xls,.xlsx" ref={fileInputRef} style={{ display: 'none' }} onChange={onImportFile} />
          <button className="btn btn-secondary" style={{ color: "var(--danger)" }} onClick={onDeleteAll} disabled={loading || isTesting}>
            <Trash2 size={14} /> Apagar Câmeras
          </button>
          <button className="btn btn-secondary" onClick={onImportClick} disabled={loading || isTesting}>
            <Plus size={14} /> Importar CSV
          </button>
          <button className="btn btn-secondary" onClick={onAdd}>
            <Plus size={14} /> Adicionar Câmera
          </button>
          <button className="btn btn-secondary" disabled={!hasImages} onClick={onDownloadImages}>
            Baixar Imagens
          </button>
          <button className="btn btn-success" disabled={loading || isTesting || cameras.length === 0} onClick={onTestAll}>
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
            {cameras.map(cam => {
              const res = testResults[cam.id];
              return (
                <tr key={cam.id} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '12px 16px' }}>{cam.name}</td>
                  <td style={{ padding: '12px 16px', fontFamily: 'monospace' }}>{cam.ip}</td>
                  <td style={{ padding: '12px 16px' }}>{cam.config_extra?.modelo || "N/A"}</td>
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
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <img src={`data:image/jpeg;base64,${res.image_base64}`} alt="Preview" style={{ maxHeight: '60px', borderRadius: '4px', border: '1px solid #ccc' }} />
                        <a href={`data:image/jpeg;base64,${res.image_base64}`} download={`camera_${safeFileName(cam.name)}.jpg`} title="Baixar Imagem" style={{ cursor: 'pointer', background: 'var(--surface-2)', padding: '6px', borderRadius: '4px', border: '1px solid var(--border)', textDecoration: 'none' }}>
                          📥
                        </a>
                      </div>
                    )}
                  </td>
                  <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                    <button className="btn btn-secondary" style={{ padding: '4px 8px', fontSize: 12, marginRight: 8 }} onClick={() => onEdit(cam)}>Editar</button>
                    <button onClick={() => onRemove(cam)} disabled={isTesting} style={{ background: 'none', border: 'none', color: '#dc2626', cursor: 'pointer', fontSize: 12 }}>Remover</button>
                  </td>
                </tr>
              );
            })}
            {cameras.length === 0 && (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: 30, color: 'var(--text-muted)' }}>Nenhuma câmera cadastrada. Use "Importar CSV" ou adicione manualmente.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
