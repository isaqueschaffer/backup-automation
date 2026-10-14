import { useRef } from "react";
import * as XLSX from "xlsx";
import { createEquipamento, deleteEquipamento } from "../../../api/client";
import { NVR } from "../../../api/types";
import { ToastFn } from "../utils";

// Parser robusto de CSV (suporta aspas e delimitadores no meio do texto)
function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  const delimiter = (text.indexOf(";") !== -1 && text.indexOf(";") < (text.indexOf("\n") === -1 ? 9999 : text.indexOf("\n"))) ? ";" : ",";

  let currentRow: string[] = [];
  let currentCell = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (i + 1 < text.length && text[i + 1] === '"') { currentCell += '"'; i++; }
        else { inQuotes = false; }
      } else { currentCell += c; }
    } else {
      if (c === '"') { inQuotes = true; }
      else if (c === delimiter) { currentRow.push(currentCell.trim()); currentCell = ""; }
      else if (c === "\n" || c === "\r") {
        if (c === "\r" && i + 1 < text.length && text[i + 1] === "\n") i++;
        currentRow.push(currentCell.trim());
        if (currentRow.some(col => col !== "")) rows.push(currentRow);
        currentRow = [];
        currentCell = "";
      } else { currentCell += c; }
    }
  }
  if (currentCell || currentRow.length > 0) {
    currentRow.push(currentCell.trim());
    if (currentRow.some(col => col !== "")) rows.push(currentRow);
  }
  return rows;
}

interface CameraRow { name: string; ip: string; password: string; modelo: string }

// Converte linhas (CSV/XLSX) em câmeras a importar
function rowsToCameras(rows: unknown[][]): CameraRow[] {
  const headers = (rows[0] || []).map(h => String(h).trim().toLowerCase());

  let idxDesc = headers.findIndex(h => h.includes("desc"));
  if (idxDesc === -1) idxDesc = headers.findIndex(h => h.includes("nome") || h.includes("câmera") || h.includes("camera"));

  const idxIp = headers.findIndex(h => h.includes("ip") || h.includes("endere"));
  const idxPass = headers.findIndex(h => h.includes("senha") || h.includes("pass"));

  const out: CameraRow[] = [];
  for (let i = 1; i < rows.length; i++) {
    const cols = rows[i];
    if (!cols || cols.length === 0 || (!cols[0] && !cols[1])) continue;

    let desc = "";
    let ender = "";
    let pass = "";

    if (idxDesc >= 0 || idxIp >= 0) {
      desc = idxDesc >= 0 ? String(cols[idxDesc] || "") : String(cols[0] || "");
      ender = idxIp >= 0 ? String(cols[idxIp] || "") : String(cols[1] || "");
      pass = idxPass >= 0 ? String(cols[idxPass] || "") : "";
    } else {
      // Fallback absoluto caso não ache nenhum cabeçalho
      desc = String(cols[1] || "");
      ender = String(cols[3] || "");
      pass = String(cols[6] || "");
    }

    // Limpar caracteres nulos (0x00) que quebram o banco de dados (PostgreSQL)
    desc = desc.replace(/\0/g, "").trim();
    ender = ender.replace(/\0/g, "").trim();
    pass = pass.replace(/\0/g, "").trim();

    const rowStr = cols.join(" ").toUpperCase();
    let modelo = "Hikvision";
    if (rowStr.includes("HIKVISION")) modelo = "Hikvision";
    else if (rowStr.includes("INTELBRAS")) modelo = "Intelbras";
    else if (rowStr.includes("GRANDSTREAM")) modelo = "Grandstream";
    else if (rowStr.includes("ONVIF")) modelo = "ONVIF";

    if (desc && ender) out.push({ name: desc, ip: ender, password: pass, modelo });
  }
  return out;
}

function summarize(ok: number, fail: number, okMsg: string, toast: ToastFn) {
  if (fail === 0) toast(okMsg, "success");
  else toast(`${ok} ok, ${fail} falharam`, ok > 0 ? "info" : "error");
}

// Importação (CSV/XLSX) e exclusão em massa de câmeras, sempre item a item
export function useCameraImport({ clientId, cameras, setBusy, reload, toast }: {
  clientId: string | undefined;
  cameras: NVR[];
  setBusy: (busy: boolean) => void;
  reload: () => void;
  toast: ToastFn;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const importFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !clientId) return;
    const isCsv = file.name.toLowerCase().endsWith(".csv");
    const reader = new FileReader();
    reader.onload = async (evt) => {
      setBusy(true);
      try {
        let rows: unknown[][] = [];
        if (isCsv) {
          rows = parseCsv(evt.target?.result as string);
        } else {
          const data = new Uint8Array(evt.target?.result as ArrayBuffer);
          const workbook = XLSX.read(data, { type: "array" });
          const sheetName = workbook.SheetNames[0];
          const worksheet = workbook.Sheets[sheetName];
          rows = XLSX.utils.sheet_to_json(worksheet, { header: 1 }) as unknown[][];
        }

        let ok = 0;
        let fail = 0;
        for (const cam of rowsToCameras(rows)) {
          try {
            await createEquipamento(clientId, {
              tipo: "CAMERA",
              name: cam.name,
              ip: cam.ip,
              username: "admin",
              password: cam.password || "navarro@123",
              config_extra: { modelo: cam.modelo },
            });
            ok++;
          } catch (err) {
            console.error(err);
            fail++;
          }
        }
        summarize(ok, fail, `Importadas ${ok} câmeras com sucesso!`, toast);
        reload();
      } catch (err) {
        console.error(err);
        toast("Erro ao importar câmeras.", "error");
      } finally {
        setBusy(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    };
    reader.onerror = () => {
      toast("Erro ao ler o arquivo.", "error");
      if (fileInputRef.current) fileInputRef.current.value = "";
    };

    if (isCsv) {
      reader.readAsText(file, "ISO-8859-1");
    } else {
      reader.readAsArrayBuffer(file);
    }
  };

  const deleteAll = async () => {
    if (!clientId) return;
    if (cameras.length === 0) return toast("Nenhuma câmera para apagar.", "error");
    if (!window.confirm(`Tem certeza que deseja apagar as ${cameras.length} câmeras? Isso não pode ser desfeito.`)) return;
    setBusy(true);
    try {
      let ok = 0;
      let fail = 0;
      for (const cam of cameras) {
        try {
          await deleteEquipamento(clientId, cam.id);
          ok++;
        } catch (err) {
          console.error(err);
          fail++;
        }
      }
      summarize(ok, fail, "Todas as câmeras foram apagadas.", toast);
      reload();
    } finally {
      setBusy(false);
    }
  };

  return { fileInputRef, importFile, deleteAll };
}
