import { useRef } from "react";
import * as XLSX from "xlsx";
import { createEquipamento, deleteEquipamento } from "../../../../api/client";
import { NVR } from "../../../../api/types";
import { ToastFn } from "../utils";

// Parser robusto de CSV (suporta aspas e delimitadores no meio do texto)
export function parseCsv(text: string): string[][] {
  text = text.replace(/^\uFEFF/, "").replace(/^ï»¿/, "");
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

export interface CameraRow { name: string; ip: string; password: string; modelo: string }

function cleanCell(val: unknown): string {
  if (val === null || val === undefined) return "";
  return String(val).replace(/^\uFEFF/, "").replace(/^ï»¿/, "").replace(/\0/g, "").trim();
}

// Converte linhas (CSV/XLSX) em câmeras a importar
export function rowsToCameras(rows: unknown[][]): CameraRow[] {
  if (!rows || rows.length === 0) return [];

  // 1. Localiza a linha do cabeçalho real (linha 0 ou linhas subsequentes se houver metadados do NVR no topo)
  let headerRowIdx = 0;
  for (let r = 0; r < Math.min(rows.length, 5); r++) {
    const rowStr = (rows[r] || []).map(c => cleanCell(c).toLowerCase());
    if (
      rowStr.some(c =>
        c.includes("ip camera address") ||
        c.includes("ip do dispositivo") ||
        c.includes("endere") ||
        c.includes("descri")
      )
    ) {
      headerRowIdx = r;
      break;
    }
  }

  const headers = (rows[headerRowIdx] || []).map(h => cleanCell(h).toLowerCase());

  // Detecção específica do NVR Hikvision (exportação nativa do equipamento DS-*)
  const isHikvisionNvr =
    headers.some(h => h.includes("ip camera address")) ||
    (rows[0] && cleanCell(rows[0][0]).toLowerCase().includes("device type"));

  const out: CameraRow[] = [];

  if (isHikvisionNvr) {
    const idxName = headers.findIndex(h => h.includes("ip camera no") || h.includes("camera no") || h === "no" || h === "nº");
    const idxIp = headers.findIndex(h => h.includes("ip camera address") || h === "ip");
    const idxProto = headers.findIndex(h => h.includes("protocol") && !h.includes("transfer"));
    const idxPass = headers.findIndex(h => h.includes("password") || h.includes("senha"));

    for (let i = headerRowIdx + 1; i < rows.length; i++) {
      const cols = rows[i];
      if (!cols || cols.length === 0) continue;

      const ip = cleanCell(idxIp >= 0 ? cols[idxIp] : cols[1]);
      // Descarta linhas sem IP, cabeçalhos repetidos ou rodapés vazios com ;;;
      if (!ip || !ip.includes(".") || ip.toLowerCase().includes("camera")) continue;

      let name = cleanCell(idxName >= 0 ? cols[idxName] : cols[0]);
      // Se o nome for apenas números (ex: "58", "195"), prefixa com CAM para ficar padronizado
      if (/^\d+$/.test(name)) {
        name = `CAM ${name.padStart(2, "0")}`;
      } else if (!name) {
        name = `CAM ${String(out.length + 1).padStart(2, "0")}`;
      }

      const pass = cleanCell(idxPass >= 0 ? cols[idxPass] : cols[6]);
      const proto = cleanCell(idxProto >= 0 ? cols[idxProto] : cols[2]).toUpperCase();

      let modelo = "Hikvision";
      if (proto.includes("INTELBRAS")) modelo = "Intelbras";
      else if (proto.includes("ONVIF") || proto.includes("MOTOROLA") || proto.includes("MTI")) modelo = "ONVIF";
      else if (proto.includes("GRANDSTREAM")) modelo = "Grandstream";

      out.push({
        name,
        ip,
        password: pass || "navarro@123",
        modelo,
      });
    }
    return out;
  }

  // Demais formatos: Digifort, Intelbras Defense e Genéricos
  let idxDesc = headers.findIndex(h => h.includes("desc"));
  let idxNome = headers.findIndex(h => h.includes("nome") || h.includes("câmera") || h.includes("camera"));
  if (idxDesc === -1) idxDesc = idxNome;

  const idxIp = headers.findIndex(h => h.includes("ip") || h.includes("endere"));
  const idxPass = headers.findIndex(h => h.includes("senha") || h.includes("pass"));
  const idxModelo = headers.findIndex(h =>
    h.includes("modelo") || h.includes("protocolo") || h.includes("protocol") || h.includes("marca") || h.includes("fabricante")
  );

  for (let i = headerRowIdx + 1; i < rows.length; i++) {
    const cols = rows[i];
    if (!cols || cols.length === 0 || (!cols[0] && !cols[1])) continue;

    let desc = "";
    let ender = "";
    let pass = "";

    if (idxDesc >= 0 || idxIp >= 0) {
      const colNome = cleanCell(idxNome >= 0 ? cols[idxNome] : cols[0]);
      const colDesc = cleanCell(idxDesc >= 0 ? cols[idxDesc] : "");
      desc = colDesc || colNome;
      if (colNome && colDesc && colNome.length > colDesc.length && !/^\d+$/.test(colNome)) {
        desc = colNome;
      }
      ender = cleanCell(idxIp >= 0 ? cols[idxIp] : cols[1]);
      pass = cleanCell(idxPass >= 0 ? cols[idxPass] : "");
    } else {
      desc = cleanCell(cols[1]) || cleanCell(cols[0]);
      ender = cleanCell(cols[3]);
      pass = cleanCell(cols[6]);
    }

    if (!ender || !ender.includes(".")) continue;

    // 1) Tenta usar a coluna modelo/protocolo/marca explícita do cabeçalho
    let modelo = "";
    if (idxModelo >= 0) {
      const cellModelo = cleanCell(cols[idxModelo]).toUpperCase();
      if (cellModelo.includes("INTELBRAS")) modelo = "Intelbras";
      else if (cellModelo.includes("HIKVISION") || cellModelo.includes("HIKV")) modelo = "Hikvision";
      else if (cellModelo.includes("GRANDSTREAM")) modelo = "Grandstream";
      else if (cellModelo.includes("ONVIF") || cellModelo.includes("MOTOROLA") || cellModelo.includes("MTI")) modelo = "ONVIF";
      else if (cellModelo) modelo = cleanCell(cols[idxModelo]); // valor literal (ex: "Dahua")
    }
    // 2) Fallback: heurística pela linha inteira (quando não há coluna dedicada ou célula vazia)
    if (!modelo) {
      const rowStr = cols.join(" ").toUpperCase();
      if (rowStr.includes("HIKVISION") || rowStr.includes("HIKV")) modelo = "Hikvision";
      else if (rowStr.includes("INTELBRAS")) modelo = "Intelbras";
      else if (rowStr.includes("GRANDSTREAM")) modelo = "Grandstream";
      else if (rowStr.includes("ONVIF") || rowStr.includes("MOTOROLA") || rowStr.includes("MTI")) modelo = "ONVIF";
      else if (rowStr.includes("CÂMERA IP") || rowStr.includes("CAMERA IP")) modelo = "Intelbras";
      else modelo = "Hikvision";
    }

    if (desc && ender) {
      out.push({ name: desc, ip: ender, password: pass || "navarro@123", modelo });
    }
  }
  return out;
}

function summarize(ok: number, fail: number, okMsg: string, toast: ToastFn) {
  if (fail === 0) toast(okMsg, "success");
  else toast(`${ok} ok, ${fail} falharam`, ok > 0 ? "info" : "error");
}

// Lê um arquivo CSV ou XLSX (planilha exportada do NVR/Digifort/Defense) e devolve as linhas brutas
export function readRowsFromFile(file: File): Promise<unknown[][]> {
  return new Promise((resolve, reject) => {
    const isCsv = file.name.toLowerCase().endsWith(".csv");
    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        if (isCsv) {
          const buf = new Uint8Array(evt.target?.result as ArrayBuffer);
          let text = "";
          try {
            text = new TextDecoder("utf-8", { fatal: true }).decode(buf);
          } catch {
            text = new TextDecoder("iso-8859-1").decode(buf);
          }
          resolve(parseCsv(text));
        } else {
          const data = new Uint8Array(evt.target?.result as ArrayBuffer);
          const workbook = XLSX.read(data, { type: "array" });
          const sheetName = workbook.SheetNames[0];
          const worksheet = workbook.Sheets[sheetName];
          resolve(XLSX.utils.sheet_to_json(worksheet, { header: 1 }) as unknown[][]);
        }
      } catch (err) {
        reject(err);
      }
    };
    reader.onerror = () => reject(new Error("Erro ao ler o arquivo."));
    reader.readAsArrayBuffer(file);
  });
}

// Importação (CSV/XLSX) e exclusão em massa de câmeras, sempre item a item
export function useCameraImport({ machineId, cameras, setBusy, reload, toast }: {
  machineId: string | undefined;
  cameras: NVR[];
  setBusy: (busy: boolean) => void;
  reload: () => void;
  toast: ToastFn;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const importFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !machineId) return;
    setBusy(true);
    try {
      const rows = await readRowsFromFile(file);
      let ok = 0;
      let fail = 0;
      for (const cam of rowsToCameras(rows)) {
        try {
          await createEquipamento(machineId, {
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

  const deleteAll = async () => {
    if (!machineId) return;
    if (cameras.length === 0) return toast("Nenhuma câmera para apagar.", "error");
    if (!window.confirm(`Tem certeza que deseja apagar as ${cameras.length} câmeras? Isso não pode ser desfeito.`)) return;
    setBusy(true);
    try {
      let ok = 0;
      let fail = 0;
      for (const cam of cameras) {
        try {
          await deleteEquipamento(machineId, cam.id);
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
