import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import api from "../../../../api/client";
import { AlarmeStatusResponse } from "../../../../api/types";
import Modal from "../../../../components/Modal";
import { fmtDate } from "../../../../utils/date";

export default function AlarmesModal({ machineId, nvrId, nvrName, onClose }: {
  machineId: string;
  nvrId: string;
  nvrName: string;
  onClose: () => void;
}) {
  const [dados, setDados] = useState<AlarmeStatusResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState("");

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro("");
    try {
      const res = await api.get<AlarmeStatusResponse>(`/machines/${machineId}/equipamentos/${nvrId}/alarmes`);
      setDados(res.data);
    } catch {
      setErro("Não foi possível carregar o status dos alarmes.");
    } finally {
      setCarregando(false);
    }
  }, [machineId, nvrId]);

  useEffect(() => {
    carregar();
    const t = setInterval(carregar, 60_000);
    return () => clearInterval(t);
  }, [carregar]);

  const centrais = dados?.alarmes || [];

  return (
    <Modal wide={true} title={`Alarmes — ${nvrName}`} onClose={onClose}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        {dados?.atualizado_em && (
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Coletado em {fmtDate(dados.atualizado_em)}</span>
        )}
        <button className="btn btn-secondary btn-sm" style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}
          onClick={carregar} disabled={carregando}>
          <RefreshCw size={13} /> Atualizar
        </button>
      </div>
      {erro ? (
        <div className="empty-state" style={{ color: "var(--err)" }}>{erro}</div>
      ) : dados?.erro ? (
        <div className="empty-state" style={{ color: "var(--err)" }}>Sem resposta da central de alarme: {dados.erro}</div>
      ) : !dados?.atualizado_em ? (
        <div className="empty-state">
          {carregando ? "Carregando..." : "Ainda sem dados. O agente envia o status a cada 5 minutos; confira se o IP, o usuário e a senha do equipamento estão corretos."}
        </div>
      ) : centrais.length === 0 ? (
        <div className="empty-state">Nenhuma central de alarme encontrada neste equipamento.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {centrais.map((central, i) => (
            <div key={`${central.nome}-${i}`} className="table-wrap">
              <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", fontWeight: 600 }}>
                {central.nome}
                <span style={{
                  fontSize: 11, fontWeight: 500, padding: "2px 8px", borderRadius: 999,
                  color: central.status === 1 ? "var(--ok)" : "var(--err)",
                  border: `1px solid ${central.status === 1 ? "var(--ok)" : "var(--err)"}`,
                }}>
                  {central.status === 1 ? "Conectada" : "Desconectada"}
                </span>
              </div>
              <table>
                <thead><tr><th>Partição</th><th>Armada</th></tr></thead>
                <tbody>
                  {central.particoes.map((p, j) => (
                    <tr key={j}>
                      <td>{p.nome}</td>
                      <td style={{ color: p.armada ? "var(--ok)" : "var(--text-muted)", fontWeight: 600 }}>
                        {p.armada ? "Armada" : "Desarmada"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}
