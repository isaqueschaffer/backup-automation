export type StatusTone = "ok" | "warn" | "err" | "muted";

const OK = new Set(["OK", "SEM_ARQUIVOS"]);
const ERRO = new Set(["ERRO", "ERROR", "ERRO_COMUNICACAO", "NAO_EXECUTOU"]);

// Classifica o status de um backup/máquina em uma cor; sem status = aguardando
export function statusTone(status: string | null | undefined): StatusTone {
  if (!status) return "muted";
  const s = status.trim().toUpperCase();
  if (OK.has(s)) return "ok";
  if (ERRO.has(s)) return "err";
  return "warn";
}

export const isStatusOk = (status: string | null | undefined): boolean => statusTone(status) === "ok";

// Devolve true para erro ou parcial; false para ok, null, EM_ANDAMENTO e demais
export function isStatusProblem(status: string | null | undefined): boolean {
  if (!status) return false;
  const s = status.trim().toUpperCase();
  return statusTone(s) === "err" || s === "PARCIAL" || s === "PARTIAL";
}
