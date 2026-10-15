import { useEffect, useRef, useState } from "react";
import api from "../../../../api/client";
import { NVR } from "../../../../api/types";
import { ToastFn, safeFileName } from "../utils";

export type RtspResult = { status: string; error?: string; image_base64?: string };

// Teste RTSP de todas as câmeras (uma por vez) e download das imagens capturadas
export function useRtspTest({ machineId, equipamentos, machineName, toast }: {
  machineId: string | undefined;
  equipamentos: NVR[];
  machineName: string | undefined;
  toast: ToastFn;
}) {
  const [isTesting, setIsTesting] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, RtspResult>>({});
  // Token da execução atual: qualquer mudança de máquina/desmontagem invalida o loop em andamento
  const runRef = useRef(0);

  useEffect(() => {
    setTestResults({});
    setIsTesting(false);
    return () => { runRef.current++; };
  }, [machineId]);

  const hasImages = Object.values(testResults).some(r => r.image_base64);

  const testAll = async () => {
    if (!machineId) return;
    const cams = equipamentos.filter(e => e.tipo === "CAMERA");
    if (cams.length === 0) return;
    const run = ++runRef.current;
    const stale = () => runRef.current !== run;
    setIsTesting(true);
    setTestResults({});

    for (const cam of cams) {
      if (stale()) return;
      setTestResults(prev => ({ ...prev, [cam.id]: { status: "testing" } }));
      try {
        const res = await api.post(`/machines/${machineId}/equipamentos/${cam.id}/test-rtsp`);
        if (stale()) return;
        if (res.data.success) {
          setTestResults(prev => ({ ...prev, [cam.id]: { status: "success", image_base64: res.data.image_base64 } }));
        } else {
          setTestResults(prev => ({ ...prev, [cam.id]: { status: "error", error: res.data.error_message } }));
        }
      } catch {
        if (stale()) return;
        setTestResults(prev => ({ ...prev, [cam.id]: { status: "error", error: "Erro de comunicação na API." } }));
      }
    }
    if (stale()) return;
    setIsTesting(false);
    toast("Teste RTSP concluído!", "success");
  };

  const downloadImages = async () => {
    const successCams = Object.entries(testResults).filter(([, res]) => res.image_base64);
    if (successCams.length === 1) {
      const [camId, res] = successCams[0];
      const cam = equipamentos.find(e => e.id === camId);
      const name = cam ? safeFileName(cam.name) : camId;
      const a = document.createElement("a");
      a.href = `data:image/jpeg;base64,${res.image_base64}`;
      a.download = `camera_${name}.jpg`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } else if (successCams.length > 1) {
      const JSZip = (await import("jszip")).default;
      const zip = new JSZip();
      successCams.forEach(([camId, res]) => {
        const cam = equipamentos.find(e => e.id === camId);
        const name = cam ? safeFileName(cam.name) : camId;
        zip.file(`camera_${name}.jpg`, res.image_base64!, { base64: true });
      });
      const blob = await zip.generateAsync({ type: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `cameras_${machineName ? safeFileName(machineName) : "maquina"}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(a.href);
    }
  };

  return { isTesting, testResults, hasImages, testAll, downloadImages };
}
