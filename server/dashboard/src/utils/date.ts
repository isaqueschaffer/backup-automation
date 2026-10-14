interface FmtDateOpts {
  /** Formato curto (dd/mm hh:mm). */
  short?: boolean;
  /** Texto quando não há data (padrão "—"). */
  empty?: string;
}

// Datas do servidor são naive em UTC (REGRA-001): acrescenta "Z" quando não há fuso.
export function fmtDate(s: string | null | undefined, opts: FmtDateOpts = {}): string {
  if (!s) return opts.empty ?? "—";
  const str = s.endsWith("Z") ? s : s + "Z";
  const d = new Date(str);
  return opts.short
    ? d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })
    : d.toLocaleString("pt-BR");
}

// Data local no formato YYYY-MM-DD (para <input type="date">), sem converter para UTC.
export function localDateStr(d: Date = new Date()): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}
