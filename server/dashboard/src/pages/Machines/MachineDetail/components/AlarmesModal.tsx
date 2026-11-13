import { useCallback, useEffect, useState } from "react";
import { Lock, LockOpen, RefreshCw } from "lucide-react";
import api, { comandarCentralAlarme } from "../../../../api/client";
import { AlarmCentral, AlarmeStatusResponse } from "../../../../api/types";
import Modal from "../../../../components/Modal";
import { useToast } from "../../../../components/Toast";
import { useConfirm } from "../../../../components/ConfirmDialog";
import { useSomenteLeitura } from "../../../../contexts/AuthContext";
import { fmtDate } from "../../../../utils/date";

const RECARREGAR_APOS_COMANDO_MS = 12_000; // o agente reenvia o status ~8s depois do comando

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

  const { toast } = useToast();
  const confirmar = useConfirm();
  const somenteLeitura = useSomenteLeitura();
  const [enviando, setEnviando] = useState<string | null>(null);

  const comandar = async (central: AlarmCentral, acao: "ARMAR" | "DESARMAR") => {
    const verbo = acao === "ARMAR" ? "Armar" : "Desarmar";
    if (central.id === null || central.id === undefined) return;
    if (!(await confirmar({
      title: `${verbo} central de alarme`,
      message: `${verbo} a central "${central.nome}"?\n\nO comando vai para a central de verdade pelo agente desta máquina.`,
      confirmLabel: verbo,
      variant: acao === "DESARMAR" ? "warning" : "info",
    }))) return;
    setEnviando(String(central.id));
    try {
      const r = await comandarCentralAlarme(machineId, nvrId, String(central.id), acao);
      if (r.sucesso) {
        toast(`${verbo}: comando aceito pela central "${central.nome}".`, "success");
        setTimeout(carregar, RECARREGAR_APOS_COMANDO_MS);
      } else {
        toast(`Não foi possível ${verbo.toLowerCase()}: ${r.mensagem || "erro desconhecido"}`, "error");
      }
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast(typeof detail === "string" ? detail : `Falha ao enviar o comando para ${verbo.toLowerCase()}.`, "error");
    } finally {
      setEnviando(null);
    }
  };

  const centrais = dados?.alarmes || [];
  const incendio = dados?.incendio || [];

  const seloStatus = (status?: number | null) => (
    <span style={{
      fontSize: 11, fontWeight: 500, padding: "2px 8px", borderRadius: 999,
      color: status === 1 ? "var(--ok)" : "var(--err)",
      border: `1px solid ${status === 1 ? "var(--ok)" : "var(--err)"}`,
    }}>
      {status === 1 ? "Conectada" : "Desconectada"}
    </span>
  );

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
          {carregando ? "Carregando..." : "Ainda sem dados. O agente envia o status a cada 5 minutos; confira o IP, o usuário e a senha do equipamento e a porta dos alarmes (padrão 3001)."}
        </div>
      ) : centrais.length === 0 && incendio.length === 0 ? (
        <div className="empty-state">Nenhuma central de alarme ou de incêndio encontrada neste equipamento.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {centrais.map((central, i) => (
            <div key={`${central.nome}-${i}`} className="table-wrap">
              <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", fontWeight: 600, flexWrap: "wrap" }}>
                {central.nome}
                {seloStatus(central.status)}
                {!somenteLeitura && central.id !== null && central.id !== undefined && (
                  <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                    {enviando === String(central.id) ? (
                      <span style={{ fontSize: 12, fontWeight: 500, color: "var(--text-muted)" }}>
                        Enviando comando pelo agente (pode levar até 1 minuto)...
                      </span>
                    ) : (
                      <>
                        <button className="btn btn-secondary btn-sm" disabled={enviando !== null}
                          onClick={() => comandar(central, "ARMAR")} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <Lock size={13} /> Armar
                        </button>
                        <button className="btn btn-secondary btn-sm" disabled={enviando !== null}
                          onClick={() => comandar(central, "DESARMAR")} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <LockOpen size={13} /> Desarmar
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>
              <table>
                <thead><tr><th>Partição</th><th>Armada</th><th>Disparo</th></tr></thead>
                <tbody>
                  {central.particoes.map((p, j) => (
                    <tr key={j}>
                      <td>{p.nome}</td>
                      <td style={{ color: p.armada ? "var(--ok)" : "var(--text-muted)", fontWeight: 600 }}>
                        {p.armada ? "Armada" : "Desarmada"}
                      </td>
                      <td style={{ color: p.disparada ? "var(--err)" : "var(--text-muted)", fontWeight: p.disparada ? 700 : 400 }}>
                        {p.disparada ? "Em disparo" : "Normal"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {incendio.length > 0 && (
            <div className="table-wrap">
              <div style={{ padding: "8px 10px", fontWeight: 600 }}>Centrais de incêndio</div>
              <table>
                <thead><tr><th>Central</th><th>Modelo</th><th>Status</th></tr></thead>
                <tbody>
                  {incendio.map((c, i) => (
                    <tr key={`${c.nome}-${i}`}>
                      <td>{c.nome}</td>
                      <td>{c.modelo || "—"}</td>
                      <td>{seloStatus(c.status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
