import { CustomerRun, CustomerRunMachine } from "../../../api/types";
import { fmtDate } from "../../../utils/date";

// Tipo da rodada em PT-BR. Avulso mostra a máquina (a única esperada).
export function runTriggerLabel(run: CustomerRun): string {
  if (run.trigger === "scheduled") return "Agendado";
  if (run.trigger === "queue") return "Fila";
  if (run.trigger === "manual_machine") {
    const name = run.machines[0]?.machine_name;
    return name ? `Avulso: ${name}` : "Avulso";
  }
  return run.trigger || "—";
}

export const isRunOpen = (run: CustomerRun) => run.status === "EM_ANDAMENTO" || !run.closed_at;

// Nome do arquivo do ZIP unificado: rodada_<cliente>_<dd-mm-aaaa_HHhMM>.zip
export function runZipFilename(customerName: string, run: CustomerRun): string {
  const when = fmtDate(run.started_at, { empty: "" })
    .replace(/\//g, "-").replace(/,?\s+/, "_").replace(/:(\d{2})(:\d{2})?$/, "h$1");
  const safeName = customerName.trim().normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[^A-Za-z0-9_-]+/g, "_");
  return `rodada_${safeName}_${when || run.id.slice(0, 8)}.zip`;
}

// Nome do arquivo do ZIP individual da máquina: backup_<nome>_<dd-mm-aaaa>.zip
export function backupZipFilename(machineName: string | null, startedAt: string | null): string {
  const safeName = (machineName || "maquina").trim().normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[^A-Za-z0-9_-]+/g, "_") || "maquina";
  const rawDate = fmtDate(startedAt, { empty: "" });
  if (!rawDate) return `backup_${safeName}.zip`;
  const datePart = rawDate.split(/,?\s+/)[0]?.replace(/\//g, "-");
  return datePart ? `backup_${safeName}_${datePart}.zip` : `backup_${safeName}.zip`;
}

// Primeira rodada (na ordem recebida) em que a máquina tem status definido
export function lastKnownStatus(
  runs: CustomerRun[],
  machineId: string
): { run: CustomerRun; entry: CustomerRunMachine } | null {
  for (const run of runs) {
    const entry = run.machines.find(m => m.machine_id === machineId);
    if (entry && entry.status !== null) {
      return { run, entry };
    }
  }
  return null;
}
