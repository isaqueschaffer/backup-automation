import { useEffect, useRef, useState } from "react";
import { Image, Moon, Upload, Video } from "lucide-react";
import api from "../../../../api/client";
import { NvrCamera } from "../../../../api/types";
import Modal from "../../../../components/Modal";
import { useToast } from "../../../../components/Toast";
import { fmtDate } from "../../../../utils/date";
import CameraImagePanel from "./CameraImagePanel";

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024; // arquivo original
const MAX_LADO = 3840; // reduz imagens maiores que 4K

type Tipo = "ref" | "noite";
type Filtro = "todas" | "sem_ref" | "sem_noite";
const TIPO_LABEL: Record<Tipo, string> = { ref: "referência", noite: "imagem da noite" };

// Converte qualquer imagem (PNG, JPG, WEBP...) em JPEG base64 (sem o prefixo data:),
// o mesmo formato da captura RTSP e dos anexos do e-mail.
function imagemParaJpegBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new window.Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      const escala = Math.min(1, MAX_LADO / Math.max(img.naturalWidth, img.naturalHeight));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.naturalWidth * escala);
      canvas.height = Math.round(img.naturalHeight * escala);
      const ctx = canvas.getContext("2d");
      if (!ctx) { reject(new Error("Navegador não conseguiu processar a imagem.")); return; }
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      resolve(canvas.toDataURL("image/jpeg", 0.9).split(",")[1]);
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Arquivo não é uma imagem válida.")); };
    img.src = url;
  });
}

function erroDaApi(e: unknown, padrao: string): string {
  // 422 do FastAPI vem como lista [{msg: "Value error, ..."}]
  const detail = (e as { response?: { data?: { detail?: string | { msg?: string }[] } } })?.response?.data?.detail;
  const msg = Array.isArray(detail) ? detail[0]?.msg?.replace(/^Value error, /, "") : detail;
  return msg || (e instanceof Error && !("response" in e) ? e.message : padrao);
}

const nomeCam = (c: NvrCamera) => c.nome || `Canal ${c.canal}`;
const temImagem = (c: NvrCamera, tipo: Tipo) => !!(tipo === "ref" ? c.perfect_image_base64 : c.night_image_base64);

function Chip({ ok, label, title }: { ok: boolean; label: string; title: string }) {
  return (
    <span title={title} style={{
      fontSize: 10, fontWeight: 700, padding: "1px 6px", borderRadius: 4, letterSpacing: "0.03em",
      background: ok ? "var(--ok-bg)" : "var(--warn-bg)", color: ok ? "var(--ok)" : "var(--warn)",
    }}>{ok ? "✓" : "✗"} {label}</span>
  );
}

export default function NVRCamerasGalleryModal({ machineId, nvrId, nvrName, onClose }: { machineId: string, nvrId: string, nvrName: string, onClose: () => void }) {
  const { toast } = useToast();
  const [cameras, setCameras] = useState<NvrCamera[]>([]);
  const [loading, setLoading] = useState(true);
  const [zoomImage, setZoomImage] = useState<{ src: string, title: string } | null>(null);
  const [selectedCanal, setSelectedCanal] = useState<number | null>(null);
  const [filtro, setFiltro] = useState<Filtro>("todas");
  // Uma captura por vez: o servidor tem uma única vaga de tarefa RTSP por máquina
  const [ocupado, setOcupado] = useState<{ tipo: Tipo | "upload"; canal: number } | null>(null);
  const [lote, setLote] = useState<{ tipo: Tipo; done: number; total: number; atual: string; falhas: string[]; fim: boolean } | null>(null);
  const cancelLote = useRef(false);
  // false após desmontar: interrompe o lote e evita setState em componente desmontado
  const aliveRef = useRef(true);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    aliveRef.current = true;
    return () => { aliveRef.current = false; cancelLote.current = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await api.get(`/machines/${machineId}/equipamentos/${nvrId}/cameras`);
        if (cancelled) return;
        setCameras(res.data);
        if (res.data?.length) setSelectedCanal(res.data[0].canal);
      } catch (e) {
        if (cancelled) return;
        console.error("Error fetching cameras:", e);
        toast("Erro ao carregar câmeras do NVR.", "error");
      }
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [machineId, nvrId, toast]);

  const atualizarCam = (canal: number, dados: Partial<NvrCamera>) =>
    setCameras(prev => prev.map(c => c.canal === canal ? { ...c, ...dados } : c));

  // Referência: ao vivo e, com a câmera offline, o quadro mais recente da gravação (agente >= 1.1.6).
  // Retorna null se deu certo, ou a mensagem de erro.
  const capturarReferencia = async (cam: NvrCamera, avisarGravacao = false): Promise<string | null> => {
    try {
      const { data } = await api.post(`/machines/${machineId}/equipamentos/${nvrId}/test-rtsp`, null,
        { params: { canal: cam.canal, modo: "referencia" } });
      if (!data.success || !data.image_base64) return data.error_message || "Falha ao capturar. Verifique se o agente está online.";
      const { data: salvo } = await api.post(`/machines/${machineId}/equipamentos/${nvrId}/cameras/perfect-image`, {
        canal: cam.canal, nome: cam.nome || "", image_base64: data.image_base64,
      });
      if (aliveRef.current) {
        atualizarCam(cam.canal, { perfect_image_base64: salvo.perfect_image_base64, id: salvo.id });
        if (avisarGravacao && data.origem === "gravacao") {
          toast(`Câmera sem vídeo ao vivo: referência tirada da gravação de ${fmtDate(data.horario)}.`, "info");
        }
      }
      return null;
    } catch (e) {
      return erroDaApi(e, "Erro ao comunicar com o servidor.");
    }
  };

  // Noite: madrugada (00h-06h) mais recente com gravação, da mais nova para a mais antiga (até 15 dias).
  // Funciona com a câmera offline; o servidor já salva como imagem da noite do canal.
  const capturarNoite = async (cam: NvrCamera): Promise<string | null> => {
    try {
      const { data } = await api.post(`/machines/${machineId}/equipamentos/${nvrId}/test-rtsp`, null,
        { params: { canal: cam.canal, modo: "noite", nome: cam.nome || "" } });
      if (data.success && data.image_base64) {
        const horario = data.horario ?? null;
        if (aliveRef.current) atualizarCam(cam.canal, {
          night_image_base64: data.image_base64, night_image_date: horario,
          captura_status: "OK", captura_motivo: undefined, captura_horario: horario,
        });
        return null;
      }
      const motivo = data.error_message || "Não foi possível capturar a imagem da noite.";
      if (aliveRef.current) atualizarCam(cam.canal, { captura_status: "FALHA", captura_motivo: motivo });
      return motivo;
    } catch (e) {
      return erroDaApi(e, "Erro ao comunicar com o servidor.");
    }
  };

  const capturarUma = async (tipo: Tipo, cam: NvrCamera) => {
    setOcupado({ tipo, canal: cam.canal });
    const erro = tipo === "ref" ? await capturarReferencia(cam, true) : await capturarNoite(cam);
    if (!aliveRef.current) return;
    if (erro) toast(erro, "error");
    else if (tipo === "noite") toast("Imagem da noite capturada.", "success");
    setOcupado(null);
  };

  const enviarArquivo = async (file: File, cam: NvrCamera) => {
    if (!file.type.startsWith("image/")) { toast("Selecione um arquivo de imagem (JPG, PNG...).", "error"); return; }
    if (file.size > MAX_UPLOAD_BYTES) { toast("Imagem muito grande (máximo 20 MB).", "error"); return; }
    setOcupado({ tipo: "upload", canal: cam.canal });
    try {
      const image_base64 = await imagemParaJpegBase64(file);
      const { data } = await api.post(`/machines/${machineId}/equipamentos/${nvrId}/cameras/perfect-image`,
        { canal: cam.canal, nome: cam.nome || "", image_base64 });
      if (aliveRef.current) {
        atualizarCam(cam.canal, { perfect_image_base64: data.perfect_image_base64, id: data.id });
        toast("Imagem de referência enviada.", "success");
      }
    } catch (e) {
      if (aliveRef.current) toast(erroDaApi(e, "Erro ao enviar a imagem."), "error");
    }
    if (aliveRef.current) setOcupado(null);
  };

  // Lote: só as câmeras sem imagem (padrão) ou todas; uma por vez, com cancelamento
  const executarLote = async (tipo: Tipo, somenteFaltantes: boolean) => {
    const alvo = cameras.filter(c => !somenteFaltantes || !temImagem(c, tipo));
    if (alvo.length === 0) { toast(`Todas as câmeras já têm ${TIPO_LABEL[tipo]}.`, "info"); return; }
    const tempo = tipo === "ref"
      ? "Leva cerca de 15 a 20 s por câmera (câmeras offline usam a gravação e podem levar até 2 min)."
      : "Busca na gravação: pode levar até 2 min por câmera.";
    const oque = somenteFaltantes ? `das ${alvo.length} câmera(s) sem ${TIPO_LABEL[tipo]}` : `de TODAS as ${alvo.length} câmera(s), substituindo as atuais`;
    if (!confirm(`Capturar a ${TIPO_LABEL[tipo]} ${oque}?\n${tempo}`)) return;

    cancelLote.current = false;
    const falhas: string[] = [];
    for (let i = 0; i < alvo.length; i++) {
      if (cancelLote.current || !aliveRef.current) break;
      const cam = alvo[i];
      setLote({ tipo, done: i, total: alvo.length, atual: nomeCam(cam), falhas: [...falhas], fim: false });
      setOcupado({ tipo, canal: cam.canal });
      const erro = tipo === "ref" ? await capturarReferencia(cam) : await capturarNoite(cam);
      if (!aliveRef.current) return;
      if (erro) falhas.push(`${nomeCam(cam)}: ${erro}`);
      setLote({ tipo, done: i + 1, total: alvo.length, atual: "", falhas: [...falhas], fim: false });
    }
    if (!aliveRef.current) return;
    setOcupado(null);
    setLote(l => l && { ...l, fim: true });
  };

  const selectedCam = cameras.find(c => c.canal === selectedCanal);
  const faltaRef = cameras.filter(c => !temImagem(c, "ref")).length;
  const faltaNoite = cameras.filter(c => !temImagem(c, "noite")).length;
  const visiveis = cameras.filter(c => filtro === "todas" || (filtro === "sem_ref" ? !temImagem(c, "ref") : !temImagem(c, "noite")));
  const travado = ocupado !== null || (lote !== null && !lote.fim);

  // Função (não componente): manter o <details> aberto entre as renderizações do lote
  const grupoLote = (tipo: Tipo, icone: React.ReactNode, titulo: string, falta: number, ajuda: string) => {
    const total = cameras.length;
    const meu = lote?.tipo === tipo ? lote : null;
    return (
      <div key={tipo} style={{ flex: 1, minWidth: 260, border: "1px solid var(--border)", borderRadius: 8, padding: "12px 14px", background: "var(--surface)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          {icone}
          <span style={{ fontWeight: 700, fontSize: 13 }}>{titulo}</span>
          <span style={{ marginLeft: "auto", fontSize: 12, color: falta ? "var(--warn)" : "var(--ok)", fontWeight: 600 }}>
            {total - falta}/{total} com imagem
          </span>
        </div>
        <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 10 }}>{ajuda}</div>
        {meu && !meu.fim ? (
          <>
            <div style={{ fontSize: 12, marginBottom: 6 }}>Capturando {meu.done + (meu.atual ? 1 : 0)}/{meu.total}{meu.atual ? ` — ${meu.atual}` : ""}…</div>
            <div style={{ height: 6, background: "var(--border)", borderRadius: 3, overflow: "hidden", marginBottom: 8 }}>
              <div style={{ width: `${(meu.done / meu.total) * 100}%`, height: "100%", background: "var(--primary)", transition: "width 0.3s" }} />
            </div>
            <button className="btn btn-secondary" style={{ width: "100%", justifyContent: "center" }}
              onClick={() => { cancelLote.current = true; }}>
              Cancelar (termina a câmera atual)
            </button>
          </>
        ) : (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary" style={{ flex: 1, justifyContent: "center" }} disabled={travado || falta === 0}
              onClick={() => executarLote(tipo, true)} title={`Captura só as câmeras que ainda não têm ${TIPO_LABEL[tipo]}`}>
              {falta === 0 ? "Nenhuma faltando" : `Capturar faltantes (${falta})`}
            </button>
            <button className="btn btn-secondary" disabled={travado || total === 0}
              onClick={() => executarLote(tipo, false)} title={`Captura de novo a ${TIPO_LABEL[tipo]} de todas as câmeras`}>
              Todas
            </button>
          </div>
        )}
        {meu?.fim && (
          <div style={{ fontSize: 12, marginTop: 8, color: meu.falhas.length ? "var(--err)" : "var(--ok)" }}>
            {meu.done < meu.total ? `Cancelado: ${meu.done} de ${meu.total} processada(s). ` : ""}
            {meu.done - meu.falhas.length} capturada(s){meu.falhas.length ? `, ${meu.falhas.length} com falha` : ""}.
            {meu.falhas.length > 0 && (
              <details style={{ marginTop: 4, color: "var(--text-muted)" }}>
                <summary style={{ cursor: "pointer" }}>Ver falhas</summary>
                <ul style={{ margin: "4px 0 0", paddingLeft: 16, maxHeight: 120, overflowY: "auto" }}>
                  {meu.falhas.map((f, i) => <li key={i}>{f}</li>)}
                </ul>
              </details>
            )}
          </div>
        )}
      </div>
    );
  };

  const filtros: { id: Filtro; label: string; n: number }[] = [
    { id: "todas", label: "Todas", n: cameras.length },
    { id: "sem_ref", label: "Sem referência", n: faltaRef },
    { id: "sem_noite", label: "Sem noite", n: faltaNoite },
  ];

  return (
    <>
      <Modal title={`Câmeras do NVR: ${nvrName}`} onClose={onClose} width="1200px">
        {loading ? (
          <div style={{ padding: 40, textAlign: "center" }}>Carregando galeria...</div>
        ) : cameras.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--text-muted)" }}>Nenhuma câmera sincronizada neste NVR ainda. Aguarde o próximo backup.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", height: "80vh", margin: "-24px" }}>
            {/* Ações em lote */}
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", padding: "14px 16px", borderBottom: "1px solid var(--border)", background: "var(--surface-50)" }}>
              {grupoLote("ref", <Image size={15} color="#10b981" />, "Referência ideal", faltaRef,
                "Anexada no e-mail quando a câmera fica offline. Ao vivo; câmera offline usa a gravação mais recente.")}
              {grupoLote("noite", <Moon size={15} color="var(--primary)" />, "Imagem da noite", faltaNoite,
                "Madrugada (00h–06h) mais recente com gravação, até 15 dias. Não roda mais durante o backup.")}
            </div>

            <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
              {/* Lateral: canais */}
              <div style={{ width: 270, borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", background: "var(--surface-50)" }}>
                <div style={{ display: "flex", gap: 4, padding: "10px 10px 8px", flexWrap: "wrap" }}>
                  {filtros.map(f => (
                    <button key={f.id} onClick={() => setFiltro(f.id)} style={{
                      fontSize: 11, fontWeight: 600, padding: "4px 8px", borderRadius: 999, cursor: "pointer",
                      border: `1px solid ${filtro === f.id ? "var(--primary)" : "var(--border)"}`,
                      background: filtro === f.id ? "var(--primary-light)" : "transparent",
                      color: filtro === f.id ? "var(--primary-dark)" : "var(--text-muted)",
                    }}>{f.label} ({f.n})</button>
                  ))}
                </div>
                <div style={{ overflowY: "auto", flex: 1 }}>
                  {visiveis.length === 0 && (
                    <div style={{ padding: 16, fontSize: 12, color: "var(--text-muted)" }}>Nenhuma câmera neste filtro.</div>
                  )}
                  {visiveis.map(cam => {
                    const isSelected = selectedCanal === cam.canal;
                    const capturando = ocupado?.canal === cam.canal;
                    return (
                      <div key={cam.canal} onClick={() => setSelectedCanal(cam.canal)}
                        style={{
                          padding: "10px 14px", cursor: "pointer", display: "flex", gap: 10,
                          background: isSelected ? "var(--primary-light)" : "transparent",
                          borderLeft: `4px solid ${isSelected ? "var(--primary)" : "transparent"}`,
                        }}
                        onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = "var(--surface-hover)"; }}
                        onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = "transparent"; }}>
                        <Video size={15} color={isSelected ? "var(--primary)" : "var(--text-muted)"} style={{ marginTop: 2, flexShrink: 0 }} />
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontWeight: isSelected ? 600 : 500, fontSize: 13, color: isSelected ? "var(--primary-dark)" : "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {nomeCam(cam)}
                          </div>
                          <div style={{ display: "flex", gap: 4, marginTop: 4, flexWrap: "wrap", alignItems: "center" }}>
                            <Chip ok={temImagem(cam, "ref")} label="REF" title={temImagem(cam, "ref") ? "Tem imagem de referência" : "Sem imagem de referência: não é anexada no e-mail se a câmera ficar offline"} />
                            <Chip ok={temImagem(cam, "noite")} label="NOITE" title={temImagem(cam, "noite") ? `Imagem da noite de ${fmtDate(cam.night_image_date)}` : (cam.captura_motivo || "Sem imagem da noite")} />
                            {cam.status_comunicacao === "OFFLINE" && (
                              <span style={{ fontSize: 10, fontWeight: 700, padding: "1px 6px", borderRadius: 4, background: "var(--err-bg)", color: "var(--err)" }}>OFFLINE</span>
                            )}
                            {capturando && <span style={{ fontSize: 10, color: "var(--primary)" }}>capturando…</span>}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Detalhe da câmera */}
              <div style={{ flex: 1, padding: 24, overflowY: "auto", background: "var(--background)" }}>
                {selectedCam ? (
                  <>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, borderBottom: "1px solid var(--border)", paddingBottom: 14, marginBottom: 20 }}>
                      <h2 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>{nomeCam(selectedCam)}</h2>
                      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Canal {selectedCam.canal}</span>
                      {selectedCam.status_comunicacao === "OFFLINE" && <span className="badge err">OFFLINE</span>}
                    </div>

                    <input ref={fileInput} type="file" accept="image/*" style={{ display: "none" }}
                      onChange={e => {
                        const f = e.target.files?.[0];
                        e.target.value = ""; // permite escolher o mesmo arquivo de novo
                        if (f) enviarArquivo(f, selectedCam);
                      }} />

                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 24 }}>
                      <div>
                        <CameraImagePanel
                          dotColor="#10b981"
                          label="REFERÊNCIA IDEAL"
                          base64={selectedCam.perfect_image_base64}
                          alt="Referência"
                          emptyText="Sem imagem de referência"
                          onZoom={src => setZoomImage({ src, title: `${nomeCam(selectedCam)} - REFERÊNCIA IDEAL` })}
                        />
                        <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                          <button className="btn btn-primary" disabled={travado} onClick={() => capturarUma("ref", selectedCam)}
                            title="Imagem ao vivo; se a câmera estiver offline, usa a gravação mais recente"
                            style={{ display: "flex", gap: 6, alignItems: "center" }}>
                            <Image size={15} />
                            {ocupado?.tipo === "ref" && ocupado.canal === selectedCam.canal ? "Capturando..." : "Capturar"}
                          </button>
                          <button className="btn btn-secondary" disabled={travado} onClick={() => fileInput.current?.click()}
                            title="Enviar uma imagem do computador como referência deste canal"
                            style={{ display: "flex", gap: 6, alignItems: "center" }}>
                            <Upload size={15} />
                            {ocupado?.tipo === "upload" && ocupado.canal === selectedCam.canal ? "Enviando..." : "Enviar imagem"}
                          </button>
                        </div>
                      </div>

                      <div>
                        <CameraImagePanel
                          dotColor="var(--primary)"
                          label={selectedCam.night_image_date ? `NOITE — ${fmtDate(selectedCam.night_image_date)}` : "IMAGEM DA NOITE"}
                          base64={selectedCam.night_image_base64}
                          alt="Noite"
                          emptyText={selectedCam.captura_motivo || "Sem imagem da noite"}
                          onZoom={src => setZoomImage({ src, title: `${nomeCam(selectedCam)} - NOITE` })}
                        />
                        <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                          <button className="btn btn-primary" disabled={travado} onClick={() => capturarUma("noite", selectedCam)}
                            title="Busca a madrugada (00h–06h) mais recente com gravação, até 15 dias atrás. Funciona com a câmera offline."
                            style={{ display: "flex", gap: 6, alignItems: "center" }}>
                            <Moon size={15} />
                            {ocupado?.tipo === "noite" && ocupado.canal === selectedCam.canal ? "Buscando na gravação..." : "Capturar da gravação"}
                          </button>
                        </div>
                      </div>
                    </div>
                  </>
                ) : (
                  <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", flexDirection: "column", gap: 16 }}>
                    <Video size={48} opacity={0.2} />
                    <span>Selecione um canal na lateral para visualizar as imagens</span>
                  </div>
                )}
              </div>
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
