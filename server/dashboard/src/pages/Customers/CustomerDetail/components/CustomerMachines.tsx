import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Archive, Download } from "lucide-react";
import { downloadBackupZip } from "../../../../api/client";
import { CustomerRun, CustomerRunMachine } from "../../../../api/types";
import StatusBadge from "../../../../components/StatusBadge";
import StatusDots from "../../../../components/StatusDots";
import { useToast } from "../../../../components/Toast";
import { fmtDate } from "../../../../utils/date";
import { extractBlobError, saveBlob } from "../../../../utils/download";
import { isStatusProblem } from "../../../../utils/statusTone";
import { backupZipFilename, lastKnownStatus } from "../runUtils";

function labelForStatus(status: string | null): string {
  if (status === null) return "Aguardando";
  switch (status.toUpperCase()) {
    case "OK":
      return "OK";
    case "PARCIAL":
    case "PARTIAL":
      return "Parcial";
    case "ERRO":
    case "ERROR":
      return "Erro";
    case "NAO_EXECUTOU":
      return "Não executou";
    case "SEM_ARQUIVOS":
      return "Apenas gravações";
    default:
      return status;
  }
}

// Situação por máquina: histórico recente em pontinhos, último status e download direto
export default function CustomerMachines({
  machines,
  runs,
}: {
  machines: { id: string; name: string }[];
  runs: CustomerRun[] | null;
}) {
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const { toast } = useToast();

  const handleDownload = async (
    machineName: string,
    ultimo: { run: CustomerRun; entry: CustomerRunMachine }
  ) => {
    const backupId = ultimo.entry.backup_id;
    if (!backupId) return;
    setDownloadingId(ultimo.entry.machine_id);
    try {
      const data = await downloadBackupZip(backupId, { direct_machine: true });
      saveBlob(data, backupZipFilename(machineName, ultimo.run.started_at));
    } catch (err) {
      toast(await extractBlobError(err), "error");
    } finally {
      setDownloadingId(null);
    }
  };

  // Rodadas da mais antiga para a mais recente para montar o histórico de pontinhos
  const chronologicalRuns = useMemo(() => {
    return runs ? [...runs].reverse() : [];
  }, [runs]);

  // Ordenação: status com falha/aviso primeiro, depois por nome
  const sortedMachines = useMemo(() => {
    if (!runs) return machines;
    return [...machines].sort((a, b) => {
      const lastA = lastKnownStatus(runs, a.id);
      const prioA = lastA && isStatusProblem(lastA.entry.status) ? 0 : 1;
      const lastB = lastKnownStatus(runs, b.id);
      const prioB = lastB && isStatusProblem(lastB.entry.status) ? 0 : 1;
      if (prioA !== prioB) return prioA - prioB;
      return a.name.localeCompare(b.name, "pt-BR");
    });
  }, [machines, runs]);

  return (
    <div style={{ marginBottom: 24 }}>
      <div className="flex items-center justify-between mb-3">
        <div className="section-title" style={{ marginBottom: 0 }}>
          <Archive size={15} style={{ flexShrink: 0 }} /> Situação por máquina
        </div>
        <Link to="/backups" className="text-sm">
          Ver todos os backups
        </Link>
      </div>

      {runs === null ? (
        <div className="loading-state">
          <div className="spinner" />
        </div>
      ) : machines.length === 0 ? (
        <div className="empty-state" style={{ padding: 32 }}>
          Nenhuma máquina neste cliente.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {sortedMachines.map((m) => {
            const historico = chronologicalRuns
              .map((run) => {
                const entry = run.machines.find((x) => x.machine_id === m.id);
                if (!entry) return null;
                const rotulo = labelForStatus(entry.status);
                return {
                  status: entry.status,
                  title: `${fmtDate(run.started_at)} · ${rotulo}`,
                };
              })
              .filter(
                (item): item is { status: string | null; title: string } => item !== null
              );

            const ultimo = lastKnownStatus(runs, m.id);
            const canDownload = Boolean(ultimo?.entry.backup_id && ultimo.entry.zip);

            return (
              <div
                key={m.id}
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-sm)",
                  backgroundColor: "var(--surface-2)",
                  padding: "10px 14px",
                  display: "grid",
                  gridTemplateColumns: "1fr auto auto auto auto",
                  alignItems: "center",
                  gap: 16,
                }}
              >
                {/* Nome da máquina com link */}
                <div className="truncate">
                  <Link
                    to={`/maquinas/${m.id}`}
                    style={{ color: "var(--text-primary)", fontWeight: 600 }}
                  >
                    {m.name}
                  </Link>
                </div>

                {/* Faixa de pontinhos dos últimos backups */}
                <div>
                  <StatusDots items={historico} />
                </div>

                {/* Último status conhecido */}
                <div>
                  {ultimo ? (
                    <StatusBadge status={ultimo.entry.status} />
                  ) : (
                    <span className="text-sm text-muted">sem rodadas</span>
                  )}
                </div>

                {/* Data do último backup */}
                <div className="text-xs text-muted">
                  {ultimo ? fmtDate(ultimo.run.started_at) : "—"}
                </div>

                {/* Botão de download do ZIP da máquina */}
                <div>
                  <button
                    className="btn-icon"
                    title={canDownload ? "Baixar ZIP da máquina" : "Nenhum ZIP disponível"}
                    disabled={!canDownload || downloadingId === m.id}
                    onClick={() => ultimo && handleDownload(m.name, ultimo)}
                  >
                    {downloadingId === m.id ? (
                      <span className="spinner spinner-sm" />
                    ) : (
                      <Download size={14} style={{ flexShrink: 0 }} />
                    )}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
