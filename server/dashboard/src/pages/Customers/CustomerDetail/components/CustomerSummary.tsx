import { CustomerRun } from "../../../../api/types";
import StatusBadge from "../../../../components/StatusBadge";
import { fmtDate } from "../../../../utils/date";
import { isStatusProblem } from "../../../../utils/statusTone";
import { lastKnownStatus } from "../runUtils";

export default function CustomerSummary({
  runs,
  machines,
}: {
  runs: CustomerRun[] | null;
  machines: { id: string; name: string }[];
}) {
  if (runs === null) return null;

  const lastRun = runs.length > 0 ? runs[0] : null;

  // Sucesso em 7 dias (rodadas fechadas)
  const sevenDaysAgo = Date.now() - 7 * 24 * 3600 * 1000;
  const recentClosedRuns = runs.filter((r) => {
    if (!r.closed_at || !r.started_at) return false;
    const iso = r.started_at.endsWith("Z") ? r.started_at : r.started_at + "Z";
    const t = new Date(iso).getTime();
    return !isNaN(t) && t >= sevenDaysAgo;
  });

  let totalExpected = 0;
  let totalOk = 0;
  for (const r of recentClosedRuns) {
    totalExpected += r.machines_expected;
    totalOk += r.machines_ok;
  }
  const has7dData = recentClosedRuns.length > 0 && totalExpected > 0;
  const pct = has7dData ? Math.round((totalOk / totalExpected) * 100) : null;
  const pctColor =
    pct === null
      ? undefined
      : pct >= 90
      ? "var(--ok)"
      : pct >= 70
      ? "var(--warn)"
      : "var(--err)";

  // Máquinas com falha (último status conhecido em erro ou aviso)
  let failedCount = 0;
  for (const m of machines) {
    const known = lastKnownStatus(runs, m.id);
    if (known && isStatusProblem(known.entry.status)) {
      failedCount++;
    }
  }

  // E-mail da última rodada fechada
  const lastClosedRun = runs.find((r) => r.closed_at !== null);

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
        gap: 12,
        marginBottom: 20,
      }}
    >
      {/* 1. Última rodada */}
      <div className="stat-card" style={{ padding: "14px 18px" }}>
        <div className="stat-label">Última rodada</div>
        <div
          style={{
            fontSize: 20,
            fontWeight: 700,
            minHeight: 28,
            display: "flex",
            alignItems: "center",
          }}
        >
          {lastRun ? <StatusBadge status={lastRun.status} /> : "—"}
        </div>
        <div className="text-xs text-muted" style={{ marginTop: 4 }}>
          {lastRun ? fmtDate(lastRun.started_at) : "Sem rodadas"}
        </div>
      </div>

      {/* 2. Sucesso em 7 dias */}
      <div className="stat-card" style={{ padding: "14px 18px" }}>
        <div className="stat-label">Sucesso em 7 dias</div>
        <div
          style={{
            fontSize: 20,
            fontWeight: 700,
            minHeight: 28,
            display: "flex",
            alignItems: "center",
            color: pctColor,
          }}
        >
          {pct !== null ? `${pct}%` : "—"}
        </div>
        <div className="text-xs text-muted" style={{ marginTop: 4 }}>
          {has7dData
            ? `${recentClosedRuns.length} ${
                recentClosedRuns.length === 1 ? "rodada" : "rodadas"
              }`
            : "—"}
        </div>
      </div>

      {/* 3. Máquinas com falha */}
      <div className="stat-card" style={{ padding: "14px 18px" }}>
        <div className="stat-label">Máquinas com falha</div>
        <div
          style={{
            fontSize: 20,
            fontWeight: 700,
            minHeight: 28,
            display: "flex",
            alignItems: "center",
            color: failedCount > 0 ? "var(--err)" : "var(--ok)",
          }}
        >
          {failedCount}
        </div>
        <div className="text-xs text-muted" style={{ marginTop: 4 }}>
          de {machines.length} {machines.length === 1 ? "máquina" : "máquinas"}
        </div>
      </div>

      {/* 4. E-mail da última rodada */}
      <div className="stat-card" style={{ padding: "14px 18px" }}>
        <div className="stat-label">E-mail da última rodada</div>
        <div
          style={{
            fontSize: 20,
            fontWeight: 700,
            minHeight: 28,
            display: "flex",
            alignItems: "center",
            color: lastClosedRun
              ? lastClosedRun.email_sent
                ? "var(--ok)"
                : "var(--err)"
              : undefined,
          }}
        >
          {lastClosedRun ? (
            lastClosedRun.email_sent ? "Enviado" : "Não enviado"
          ) : (
            "—"
          )}
        </div>
        <div className="text-xs text-muted" style={{ marginTop: 4 }}>
          {lastClosedRun ? fmtDate(lastClosedRun.started_at) : "—"}
        </div>
      </div>
    </div>
  );
}
