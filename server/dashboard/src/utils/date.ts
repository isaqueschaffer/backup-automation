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

// Horário diário de backup (HH:MM)
export function fmtSchedule(hour: number, minute: number): string {
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

// Data local no formato YYYY-MM-DD (para <input type="date">), sem converter para UTC.
export function localDateStr(d: Date = new Date()): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

// Só a data (dd/mm/aaaa) de um datetime naive UTC do servidor.
export function fmtDay(s: string | null | undefined, empty = "—"): string {
  if (!s) return empty;
  return new Date(s.endsWith("Z") ? s : s + "Z").toLocaleDateString("pt-BR");
}

// Formata o tempo que a câmera está offline (Regra D).
export function fmtOfflineHa(segundos: number | null | undefined, aprox = false): string {
  if (segundos == null || isNaN(segundos)) return "";
  const s = Math.max(0, Math.floor(segundos));
  let texto: string;
  if (s < 60) {
    texto = "há menos de 1 min";
  } else if (s < 3600) {
    texto = `há ${Math.floor(s / 60)} min`;
  } else if (s < 86400) {
    texto = `há ${Math.floor(s / 3600)}h`;
  } else {
    const d = Math.floor(s / 86400);
    texto = d === 1 ? "há 1 dia" : `há ${d} dias`;
  }

  if (aprox && texto.startsWith("há ")) {
    return "há mais de " + texto.slice(3);
  }
  return texto;
}
