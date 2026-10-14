import { useEffect, useRef, useState } from "react";
import { Image, Video } from "lucide-react";
import api from "../../../../api/client";
import { NvrCamera } from "../../../../api/types";
import Modal from "../../../../components/Modal";
import { useToast } from "../../../../components/Toast";
import { fmtDate } from "../../../../utils/date";
import CameraImagePanel from "./CameraImagePanel";

export default function NVRCamerasGalleryModal({ machineId, nvrId, nvrName, onClose }: { machineId: string, nvrId: string, nvrName: string, onClose: () => void }) {
  const { toast } = useToast();
  const [cameras, setCameras] = useState<NvrCamera[]>([]);
  const [loading, setLoading] = useState(true);
  const [zoomImage, setZoomImage] = useState<{ src: string, title: string } | null>(null);
  const [selectedCanal, setSelectedCanal] = useState<number | null>(null);
  const [testingCanal, setTestingCanal] = useState<number | null>(null);
  // Atualiza a referência de todas as câmeras disponíveis (não OFFLINE), uma por vez:
  // o servidor tem uma única vaga de tarefa RTSP por máquina.
  const [bulk, setBulk] = useState<{ done: number; total: number; falhas: string[] } | null>(null);
  const cancelBulk = useRef(false);
  // false após desmontar: interrompe o loop em lote e evita setState em componente desmontado
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    return () => { aliveRef.current = false; cancelBulk.current = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const fetchCams = async () => {
      setLoading(true);
      try {
        const res = await api.get(`/machines/${machineId}/equipamentos/${nvrId}/cameras`);
        if (cancelled) return;
        setCameras(res.data);
        if (res.data && res.data.length > 0) {
          setSelectedCanal(res.data[0].canal);
        }
      } catch (e) {
        if (cancelled) return;
        console.error("Error fetching cameras:", e);
        toast("Erro ao carregar câmeras do NVR.", "error");
      }
      if (!cancelled) setLoading(false);
    };
    fetchCams();
    return () => { cancelled = true; };
  }, [machineId, nvrId, toast]);

  // Captura e salva a referência de um canal. Retorna null se deu certo, ou a mensagem de erro.
  const capturarReferencia = async (canal: number, nome: string): Promise<string | null> => {
    try {
      const resRtsp = await api.post(`/machines/${machineId}/equipamentos/${nvrId}/test-rtsp?canal=${canal}`);
      const dataRtsp = resRtsp.data;
      if (!dataRtsp.success || !dataRtsp.image_base64) {
        return dataRtsp.error_message || "Falha ao capturar imagem. Verifique se o Agente está online.";
      }
      const resSave = await api.post(`/machines/${machineId}/equipamentos/${nvrId}/cameras/perfect-image`, {
        canal, nome, image_base64: dataRtsp.image_base64
      });
      const savedCam = resSave.data;
      if (aliveRef.current) {
        setCameras(prev => prev.map(c => c.canal === canal ? { ...c, perfect_image_base64: savedCam.perfect_image_base64, id: savedCam.id } : c));
      }
      return null;
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      return detail || "Erro ao comunicar com o servidor.";
    }
  };

  const capturePerfectImage = async (canal: number, nome: string) => {
    setTestingCanal(canal);
    const erro = await capturarReferencia(canal, nome);
    if (!aliveRef.current) return;
    if (erro) toast(erro, "error");
    setTestingCanal(null);
  };

  const updateAllReferences = async () => {
    const alvo = cameras.filter(c => c.status_comunicacao !== "OFFLINE");
    if (alvo.length === 0) { toast("Nenhuma câmera disponível para atualizar.", "info"); return; }
    if (!confirm(`Atualizar a imagem de referência de ${alvo.length} câmera(s)?\nLeva cerca de 15 a 20 segundos por câmera.`)) return;
    cancelBulk.current = false;
    const falhas: string[] = [];
    setBulk({ done: 0, total: alvo.length, falhas });
    for (let i = 0; i < alvo.length; i++) {
      if (cancelBulk.current || !aliveRef.current) break;
      const cam = alvo[i];
      setTestingCanal(cam.canal);
      const erro = await capturarReferencia(cam.canal, cam.nome || "");
      if (!aliveRef.current) return;
      if (erro) falhas.push(`${cam.nome || `Canal ${cam.canal}`}: ${erro}`);
      setBulk({ done: i + 1, total: alvo.length, falhas: [...falhas] });
    }
    if (aliveRef.current) setTestingCanal(null);
  };

  const selectedCam = cameras.find(c => c.canal === selectedCanal);

  return (
    <>
      <Modal title={`Câmeras do NVR: ${nvrName}`} onClose={onClose} width="1200px">
        {loading ? (
          <div style={{ padding: 40, textAlign: "center" }}>Carregando galeria...</div>
        ) : cameras.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--text-muted)" }}>Nenhuma câmera sincronizada neste NVR ainda. Aguarde o próximo backup.</div>
        ) : (
          <div style={{ display: "flex", height: "75vh", margin: "-24px" }}>
            {/* Sidebar with Channels */}
            <div style={{ width: "260px", borderRight: "1px solid var(--border)", overflowY: "auto", padding: "16px 0", background: "var(--surface-50)" }}>
              <div style={{ padding: "0 16px", marginBottom: 12, fontSize: 12, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.05em" }}>
                CANAIS ({cameras.length})
              </div>
              <div style={{ padding: "0 16px", marginBottom: 12 }}>
                {bulk && bulk.done < bulk.total && !cancelBulk.current ? (
                  <>
                    <div style={{ fontSize: 12, marginBottom: 6 }}>Atualizando referências {bulk.done}/{bulk.total}...</div>
                    <div style={{ height: 6, background: "var(--border)", borderRadius: 3, overflow: "hidden", marginBottom: 8 }}>
                      <div style={{ width: `${(bulk.done / bulk.total) * 100}%`, height: "100%", background: "var(--primary)", transition: "width 0.3s" }} />
                    </div>
                    <button className="btn btn-secondary" style={{ width: "100%", justifyContent: "center" }}
                      onClick={() => { cancelBulk.current = true; setBulk(b => b && { ...b, total: b.done }); }}>
                      Cancelar
                    </button>
                  </>
                ) : (
                  <button className="btn btn-secondary" style={{ width: "100%", justifyContent: "center", gap: 6 }}
                    onClick={updateAllReferences} disabled={testingCanal !== null}>
                    <Image size={14} /> Atualizar todas as referências
                  </button>
                )}
                {bulk && bulk.done === bulk.total && (
                  <div style={{ fontSize: 12, marginTop: 8, color: bulk.falhas.length ? "var(--err)" : "var(--ok)" }}
                    title={bulk.falhas.join("\n")}>
                    {bulk.falhas.length
                      ? `${bulk.total - bulk.falhas.length} atualizada(s), ${bulk.falhas.length} falhou(aram) — passe o mouse para ver`
                      : `${bulk.total} referência(s) atualizada(s)`}
                  </div>
                )}
              </div>
              {cameras.map(cam => {
                const isSelected = selectedCanal === cam.canal;
                return (
                  <div
                    key={cam.canal}
                    style={{
                      padding: "12px 16px", cursor: "pointer", display: "flex", alignItems: "flex-start", gap: 12,
                      background: isSelected ? "var(--primary-light)" : "transparent",
                      borderLeft: `4px solid ${isSelected ? "var(--primary)" : "transparent"}`,
                      transition: "all 0.2s"
                    }}
                    onClick={() => setSelectedCanal(cam.canal)}
                    onMouseEnter={(e) => { if(!isSelected) e.currentTarget.style.background = "var(--surface-hover)" }}
                    onMouseLeave={(e) => { if(!isSelected) e.currentTarget.style.background = "transparent" }}
                  >
                    <Video size={16} color={isSelected ? "var(--primary)" : "var(--text-muted)"} style={{ marginTop: 2 }} />
                    <div style={{ display: "flex", flexDirection: "column" }}>
                      <span style={{ fontWeight: isSelected ? 600 : 500, color: isSelected ? "var(--primary-dark)" : "var(--text)" }}>
                        {cam.nome || `Canal ${cam.canal}`}
                      </span>
                      <div style={{ fontSize: 11, marginTop: 4, display: "flex", alignItems: "center" }}>
                        {cam.status_comunicacao === "OFFLINE" ? (
                          <span style={{ background: "var(--err-bg)", color: "var(--err)", padding: "2px 6px", borderRadius: 4, fontWeight: 600 }}>OFFLINE</span>
                        ) : cam.captura_status === "OK" ? (
                          <span style={{ color: "var(--ok)", fontWeight: 500 }}>Imagem capturada</span>
                        ) : cam.captura_status === "FALHA" ? (
                          <span style={{ color: "var(--err)", fontWeight: 500 }} title={cam.captura_motivo}>Falhou: {cam.captura_motivo?.substring(0, 15)}...</span>
                        ) : cam.captura_status === "SEM_GRAVACAO" ? (
                          <span style={{ color: "var(--text-muted)" }}>Sem gravação na madrugada</span>
                        ) : (
                          <span style={{ color: "var(--text-muted)" }}>Sem imagem</span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Main Content Area */}
            <div style={{ flex: 1, padding: 32, overflowY: "auto", display: "flex", flexDirection: "column", gap: 24, background: "var(--background)" }}>
              {selectedCam ? (
                <>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border)", paddingBottom: 16 }}>
                    <div>
                      <h2 style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>{selectedCam.nome || `Canal ${selectedCam.canal}`}</h2>
                      <p style={{ margin: "4px 0 0 0", color: "var(--text-muted)", fontSize: 14 }}>
                        Último backup: {selectedCam.captura_horario || selectedCam.night_image_date ? fmtDate(selectedCam.captura_horario || selectedCam.night_image_date) : "Desconhecido"}
                      </p>
                    </div>
                    <button
                      className="btn btn-primary"
                      onClick={() => capturePerfectImage(selectedCam.canal, selectedCam.nome || "")}
                      disabled={testingCanal === selectedCam.canal}
                      style={{ display: "flex", gap: 8, alignItems: "center" }}
                    >
                      <Image size={16} />
                      {testingCanal === selectedCam.canal ? "Capturando..." : "Atualizar Imagem de Referência"}
                    </button>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
                    <CameraImagePanel
                      dotColor="#10b981"
                      label="REFERÊNCIA IDEAL (PERFECT IMAGE)"
                      base64={selectedCam.perfect_image_base64}
                      alt="Perfect"
                      emptyText="Sem imagem de referência"
                      onZoom={(src) => setZoomImage({ src, title: `${selectedCam.nome || `Canal ${selectedCam.canal}`} - REFERÊNCIA IDEAL` })}
                    />
                    <CameraImagePanel
                      dotColor="var(--primary)"
                      label="ÚLTIMO BACKUP GRAVADO (NOITE)"
                      base64={selectedCam.night_image_base64}
                      alt="Night"
                      emptyText={selectedCam.captura_motivo || "Sem imagem (motivo não informado)"}
                      onZoom={(src) => setZoomImage({ src, title: `${selectedCam.nome || `Canal ${selectedCam.canal}`} - ÚLTIMO BACKUP` })}
                    />
                  </div>
                </>
              ) : (
                <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", flexDirection: "column", gap: 16 }}>
                  <Video size={48} opacity={0.2} />
                  <span>Selecione um canal na lateral para visualizar as imagens</span>
                </div>
              )}
            </div>
          </div>
        )}
      </Modal>

      {zoomImage && (
        <div
          style={{ position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.9)", zIndex: 999999, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", cursor: "zoom-out", padding: 40 }}
          onClick={() => setZoomImage(null)}
        >
          <div style={{ color: "white", fontSize: 20, fontWeight: 600, marginBottom: 20, letterSpacing: "0.02em" }}>{zoomImage.title}</div>
          <img src={zoomImage.src} style={{ maxWidth: "100%", maxHeight: "85vh", objectFit: "contain", borderRadius: 8, boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)" }} />
        </div>
      )}
    </>
  );
}
