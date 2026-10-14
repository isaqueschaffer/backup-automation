import { CustomerRun } from "../../../api/types";
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
  const safeName = customerName.trim().normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^A-Za-z0-9_-]+/g, "_");
  return `rodada_${safeName}_${when || run.id.slice(0, 8)}.zip`;
}
