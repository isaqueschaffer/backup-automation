import { StatusConta, TipoConta, Papel } from "../../api/types";
import { fmtDay, localDateStr } from "../../utils/date";

export function StatusContaBadge({ status }: { status: StatusConta }) {
  switch (status) {
    case "OK":
      return <span className="badge ok">Em dia</span>;
    case "AVISO":
      return <span className="badge warn">Vence em breve</span>;
    case "CRITICO":
      return <span className="badge err">Vencendo</span>;
    case "VENCIDA":
      return <span className="badge err">Vencida</span>;
    case "SUSPENSA":
      return <span className="badge err">Suspensa</span>;
    case "VITALICIA":
      return <span className="badge muted">Sem validade</span>;
    default:
      return <span className="badge muted">{status}</span>;
  }
}

export const TIPO_CONTA_LABEL: Record<TipoConta, string> = {
  INTEGRADOR: "Integrador",
  CLIENTE_FINAL: "Cliente final",
};

export const PAPEL_LABEL: Record<Papel, string> = {
  SUPER_ADMIN: "Administrador da plataforma",
  ADMIN: "Administrador",
  LEITURA: "Somente leitura",
};

export function textoValidade(c: {
  expira_em: string | null;
  dias_restantes: number | null;
  status: StatusConta;
}): string {
  if (!c.expira_em) return "Sem validade";
  if (c.status === "VENCIDA" || (c.dias_restantes !== null && c.dias_restantes < 0)) {
    return `${fmtDay(c.expira_em)} (venceu)`;
  }
  const d = c.dias_restantes ?? 0;
  return `${fmtDay(c.expira_em)} (${d === 1 ? "1 dia" : `${d} dias`})`;
}

// Dia local (YYYY-MM-DD, para <input type="date">) de um expira_em naive UTC; o mesmo dia que fmtDay mostra
export function diaLocalDaValidade(expiraEm: string | null | undefined): string {
  if (!expiraEm) return "";
  return localDateStr(new Date(expiraEm.endsWith("Z") ? expiraEm : expiraEm + "Z"));
}

export function fimDoDiaBrasilia(dataYmd: string): string {
  return `${dataYmd}T23:59:59-03:00`;
}
