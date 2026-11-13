import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import api from "../../../../api/client";
import { ConexaoTeste, OltStatus, OltStatusResponse } from "../../../../api/types";
import Modal from "../../../../components/Modal";
import { usePodeTestar } from "../../../../contexts/AuthContext";
import StatusBadge from "../../../../components/StatusBadge";
import { useToast } from "../../../../components/Toast";
import { fmtDate } from "../../../../utils/date";
import { fmtCronometro, percentualTeste, useTesteConexao } from "../useTesteConexao";
import { serverUtcMs } from "../utils";

const INTERVALO_COLETA_S = 300; // o agente lê as OLTs a cada 5 min (INTERVALO_OLT_S no agente)

// "há 3 min" / "há 1 h 05 min", a partir de segundos
function fmtIdade(seg: number): string {
  const s = Math.max(0, Math.floor(seg));
  if (s < 60) return "agora há pouco";
  if (s < 3600) return `há ${Math.floor(s / 60)} min`;
  return `há ${Math.floor(s / 3600)} h ${String(Math.floor((s % 3600) / 60)).padStart(2, "0")} min`;
}

const TEMPERATURA_ALERTA = 48;
const MAX_LINHAS_ONUS = 300;
const ESTADOS = ["ONLINE", "OFFLINE", "SEM_ENERGIA", "FALHA"] as const;
const ROTULO_ESTADO: Record<(typeof ESTADOS)[number], string> = {
  ONLINE: "Online", OFFLINE: "Offline", SEM_ENERGIA: "Sem energia", FALHA: "Fibra desconectada",
};

function Tile({ titulo, valor, cor }: { titulo: string; valor: number | string; cor?: string }) {
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", padding: "8px 14px", minWidth: 96 }}>
      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{titulo}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: cor || "var(--text-primary)" }}>{valor}</div>
    </div>
  );
}

function OltPainel({ olt, licenca }: { olt: OltStatus; licenca?: OltStatusResponse["licenca"] }) {
  const [filtro, setFiltro] = useState<string>("");
  const [busca, setBusca] = useState("");

  if (olt.erro) {
    return <div className="empty-state" style={{ color: "var(--err)" }}>Sem resposta da OLT {olt.nome} ({olt.ip}): {olt.erro}</div>;
  }
  const t = olt.totais;
  const quente = olt.temperatura != null && olt.temperatura >= TEMPERATURA_ALERTA;
  const termo = busca.trim().toLowerCase();
  const onus = (olt.onus || []).filter(o =>
    (!filtro || o.estado === filtro) &&
    (!termo || `${o.slot}/${o.pon}`.includes(termo) || o.indice.includes(termo) || (o.nome || "").toLowerCase().includes(termo) ||
      (o.serial || "").toLowerCase().includes(termo) || (o.mac || "").toLowerCase().includes(termo)));
  const temSerial = (olt.onus || []).some(o => o.tipo || o.serial);
  const temMac = (olt.onus || []).some(o => o.mac);
  const temOptico = (olt.onus || []).some(o => o.sinal_olt_dbm != null || o.sinal_onu_dbm != null);
  const ehHuawei = (olt.fabricante || "").toUpperCase() === "HUAWEI";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {(t || licenca || olt.nomes || olt.temperatura != null) && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          {t && <Tile titulo="ONUs" valor={t.total} />}
          {t && <Tile titulo="Online" valor={t.online} cor="var(--ok)" />}
          {t && <Tile titulo="Offline" valor={t.offline} cor={t.offline ? "var(--err)" : undefined} />}
          {t && <Tile titulo="Sem energia" valor={t.sem_energia} cor={t.sem_energia ? "var(--warn)" : undefined} />}
          {t && t.falha > 0 && <Tile titulo="Fibra desconectada" valor={t.falha} cor="var(--warn)" />}
          {t && <Tile titulo="Sinal ruim" valor={t.sinal_ruim ?? "—"} cor={t.sinal_ruim ? "var(--err)" : undefined} />}
          {licenca && (
            <Tile titulo="Licença UNM2000"
              valor={licenca.dias_restantes >= 0 ? `${licenca.dias_restantes} dias` : "vencida"}
              cor={licenca.dias_restantes < 0 ? "var(--err)" : licenca.dias_restantes <= 30 ? "var(--warn)" : undefined} />
          )}
          {olt.nomes && <Tile titulo="Sem nome" valor={olt.nomes.sem_nome} cor={olt.nomes.sem_nome ? "var(--warn)" : undefined} />}
          {olt.temperatura != null && <Tile titulo="Temperatura" valor={`${olt.temperatura} °C`} cor={quente ? "var(--err)" : undefined} />}
        </div>
      )}
      <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
        {olt.nome} · {olt.ip}{olt.modelo && ` · ${olt.modelo}`}{olt.controladora && ` · controladora ${olt.controladora.tipo} ${olt.controladora.software ?? ""}`}{olt.firmware && ` · firmware ${olt.firmware}${olt.hardware ? ` (hardware ${olt.hardware})` : ""}`} · coletado em {fmtDate(olt.coletado_em)}
        {olt.total_onus_olt != null && ` · ${olt.total_onus_olt} ONUs segundo a OLT`}
      </div>

      {olt.nomes?.erro && (
        <div style={{ fontSize: 12, color: "var(--err)" }}>Nomes das ONUs indisponíveis: {olt.nomes.erro}</div>
      )}
      {olt.nomes && !olt.nomes.erro && olt.nomes.sem_nome > 0 && (
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
          {olt.nomes.sem_nome} ONU(s) sem nome cadastrado na UNM2000 (a UNM só tem o nome automático da posição). Dê um nome a elas na UNM2000 e ele aparece aqui.
        </div>
      )}

      {(olt.por_pon || []).length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Slot / PON</th><th>TX da porta</th><th>Temp. GBIC</th><th>Total</th><th>Online</th><th>Offline</th><th>Sem energia</th><th>Sinal ruim</th></tr></thead>
            <tbody>
              {olt.por_pon!.map(p => (
                <tr key={`${p.slot}-${p.pon}`}>
                  <td>{p.slot ?? "?"} / {p.pon ?? "?"}</td>
                  <td>{p.tx_dbm != null ? `${p.tx_dbm.toFixed(2)} dBm` : "—"}</td>
                  <td style={{ color: p.temperatura_gbic != null && p.temperatura_gbic >= TEMPERATURA_ALERTA ? "var(--err)" : undefined }}>
                    {p.temperatura_gbic != null ? `${p.temperatura_gbic.toFixed(1)} °C` : "—"}
                  </td>
                  <td>{p.total}</td>
                  <td>{p.online}</td>
                  <td style={{ color: p.offline ? "var(--err)" : undefined }}>{p.offline}</td>
                  <td style={{ color: p.sem_energia ? "var(--warn)" : undefined }}>{p.sem_energia}</td>
                  <td style={{ color: p.sinal_ruim ? "var(--err)" : undefined }}>{p.sinal_ruim ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(olt.placas || []).length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Placa (slot)</th><th>Tipo</th><th>Hardware</th><th>Software</th></tr></thead>
            <tbody>
              {olt.placas!.map((p, i) => (
                <tr key={i}>
                  <td>{p.slot ?? "—"}</td>
                  <td>{p.tipo ?? "—"}</td>
                  <td style={{ fontSize: 12 }}>{p.hardware ?? "—"}</td>
                  <td style={{ fontSize: 12 }}>{p.software ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div>
        <div style={{ display: "flex", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
          <select className="form-input" style={{ width: 160 }} value={filtro} onChange={e => setFiltro(e.target.value)}>
            <option value="">Todos os estados</option>
            {ESTADOS.map(e => <option key={e} value={e}>{ROTULO_ESTADO[e]}</option>)}
          </select>
          <input className="form-input" style={{ width: 200 }} placeholder={temMac ? "Buscar nome ou MAC" : "Buscar nome, slot/PON ou serial"}
            value={busca} onChange={e => setBusca(e.target.value)} />
          <span style={{ fontSize: 12, color: "var(--text-muted)", alignSelf: "center" }}>{onus.length} ONU(s)</span>
        </div>
        <div className="table-wrap">
          <table>
            {temMac ? (
              <>
                <thead><tr><th>ONU ID</th><th>MAC</th><th>Descrição</th><th>Status</th><th>Temperatura</th><th>RX Power</th></tr></thead>
                <tbody>
                  {onus.slice(0, MAX_LINHAS_ONUS).map(o => (
                    <tr key={o.indice}>
                      <td style={{ fontFamily: "monospace", fontSize: 12 }}>{o.indice}</td>
                      <td style={{ fontFamily: "monospace", fontSize: 12 }}>{o.mac ?? "—"}</td>
                      <td>{o.nome ?? "—"}</td>
                      <td><StatusBadge status={o.estado} /></td>
                      <td style={{ color: o.temperatura_onu != null && o.temperatura_onu >= TEMPERATURA_ALERTA ? "var(--err)" : undefined }}>
                        {o.temperatura_onu != null ? `${o.temperatura_onu.toFixed(1)} °C` : "—"}
                      </td>
                      <td style={{ color: o.qualidade === "RUIM" ? "var(--err)" : o.qualidade === "ATENCAO" ? "var(--warn)" : undefined }}>
                        {o.sinal_onu_dbm != null ? `${o.sinal_onu_dbm.toFixed(2)} dBm` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </>
            ) : (
              <>
                <thead>
                  <tr>
                    <th>Nome</th><th>ONU (slot/PON/nº)</th>
                    {temSerial && <th>Tipo</th>}
                    {temSerial && <th>Serial</th>}
                    {temOptico && !ehHuawei && <th>Sinal na OLT</th>}
                    {temOptico && <th>Sinal na ONU</th>}
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {onus.slice(0, MAX_LINHAS_ONUS).map(o => (
                    <tr key={o.indice}>
                      <td>{o.nome ?? "—"}</td>
                      <td style={{ fontFamily: "monospace", fontSize: 12 }}>{o.indice}</td>
                      {temSerial && <td>{o.tipo ?? "—"}</td>}
                      {temSerial && <td style={{ fontFamily: "monospace", fontSize: 12 }}>{o.serial ?? "—"}</td>}
                      {temOptico && !ehHuawei && (
                        <td style={{ color: o.qualidade === "RUIM" ? "var(--err)" : o.qualidade === "ATENCAO" ? "var(--warn)" : undefined }}>
                          {o.sinal_olt_dbm != null ? `${o.sinal_olt_dbm.toFixed(2)} dBm` : "—"}
                        </td>
                      )}
                      {temOptico && <td>{o.sinal_onu_dbm != null ? `${o.sinal_onu_dbm.toFixed(2)} dBm` : "—"}</td>}
                      <td><StatusBadge status={o.estado} /></td>
                    </tr>
                  ))}
                </tbody>
              </>
            )}
          </table>
        </div>
        {onus.length > MAX_LINHAS_ONUS && (
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 6 }}>
            Mostrando {MAX_LINHAS_ONUS} de {onus.length}. Use o filtro ou a busca para ver as demais.
          </div>
        )}
      </div>
    </div>
  );
}

export default function OltStatusModal({ machineId, nvrId, nvrName, onClose }: {
  machineId: string;
  nvrId: string;
  nvrName: string;
  onClose: () => void;
}) {
  const [dados, setDados] = useState<OltStatusResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState("");
  const [ativa, setAtiva] = useState(0);
  const [agoraMs, setAgoraMs] = useState(() => Date.now());
  const { toast } = useToast();

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro("");
    try {
      const res = await api.get<OltStatusResponse>(`/machines/${machineId}/equipamentos/${nvrId}/olt-status`);
      setDados(res.data);
    } catch {
      setErro("Não foi possível carregar o status das OLTs.");
    } finally {
      setCarregando(false);
    }
  }, [machineId, nvrId]);

  useEffect(() => {
    carregar();
    const t = setInterval(carregar, 60_000);
    return () => clearInterval(t);
  }, [carregar]);

  // "Atualizar" pede ao agente uma leitura nova da OLT agora (antes só relia o último status salvo, o que
  // era instantâneo e deixava a tela igual, sem nenhum sinal de que algo aconteceu)
  const aoConcluir = useCallback((t: ConexaoTeste | null) => {
    carregar();
    if (!t) toast("Não foi possível acompanhar a atualização.", "error");
    else if (t.ok) toast(`Status atualizado em ${t.segundos} s.`, "success");
    else toast(t.mensagem || "A atualização falhou.", "error");
  }, [carregar, toast]);
  const leitura = useTesteConexao(machineId, nvrId, { onConcluido: aoConcluir });
  const podeTestar = usePodeTestar();

  // relógio para a idade do dado e a contagem até a próxima coleta automática
  useEffect(() => {
    const t = setInterval(() => setAgoraMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const idadeS = dados?.atualizado_em ? (agoraMs - serverUtcMs(dados.atualizado_em)) / 1000 : null;
  const proximaS = idadeS === null ? null : INTERVALO_COLETA_S - idadeS;
  const rotuloLeitura = leitura.teste?.etapas.find(e => e.estado === "andamento")?.rotulo || "Pedindo ao agente da máquina...";

  const olts = dados?.olts || [];
  const olt = olts[Math.min(ativa, olts.length - 1)];

  return (
    <Modal wide={true} title={`OLTs e ONUs — ${nvrName}`} onClose={onClose}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        {olts.map((o, i) => (
          <button key={o.ip} className={`btn btn-sm ${i === ativa ? "btn-primary" : "btn-secondary"}`} onClick={() => setAtiva(i)}>
            {o.nome}{o.erro ? " ⚠" : ""}
          </button>
        ))}
        {podeTestar && <button className="btn btn-secondary btn-sm" style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}
          onClick={leitura.iniciar} disabled={leitura.emAndamento}
          title="Pede ao agente da máquina uma leitura nova da OLT agora">
          <RefreshCw size={13} style={leitura.emAndamento ? { animation: "spin 0.9s linear infinite" } : undefined} />
          {leitura.emAndamento ? "Atualizando..." : "Atualizar"}
        </button>}
      </div>
      {leitura.emAndamento ? (
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 6, gap: 12 }}>
            <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{rotuloLeitura}</span>
            <span style={{ fontFamily: "monospace", color: "var(--text-muted)" }}>{fmtCronometro(leitura.segundos)}</span>
          </div>
          <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percentualTeste(leitura.teste))}
            style={{ height: 8, borderRadius: 999, background: "var(--surface-2, rgba(255,255,255,0.06))", border: "1px solid var(--border)", overflow: "hidden" }}>
            <div className="barra-progresso-ativa"
              style={{ width: `${percentualTeste(leitura.teste)}%`, height: "100%", background: "var(--accent)", borderRadius: 999, transition: "width 0.5s ease" }} />
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 5 }}>
            O agente está lendo a OLT agora; com muitas ONUs pode levar alguns minutos. Pode fechar esta janela, a leitura continua.
          </div>
        </div>
      ) : leitura.terminado && (leitura.erro || (leitura.teste && !leitura.teste.ok)) ? (
        <div style={{ marginBottom: 12, padding: "8px 12px", borderRadius: "var(--radius-sm)", fontSize: 12, background: "var(--err-bg)", color: "var(--err)" }}>
          Não foi possível atualizar: {leitura.erro || leitura.teste?.mensagem}
        </div>
      ) : (
        <div style={{ marginBottom: 12, fontSize: 12, color: "var(--text-muted)" }}>
          {idadeS === null
            ? "Ainda não há leitura desta OLT."
            : `Última leitura: ${fmtDate(dados?.atualizado_em, { short: true })} (${fmtIdade(idadeS)})`
              + (proximaS !== null && proximaS > 0 ? ` · próxima automática em ${fmtCronometro(proximaS)}` : " · próxima leitura automática a qualquer momento")}
          {leitura.terminado && leitura.teste?.ok && <span style={{ color: "var(--ok)" }}> · atualizado em {leitura.teste.segundos} s</span>}
        </div>
      )}
      {erro ? (
        <div className="empty-state" style={{ color: "var(--err)" }}>{erro}</div>
      ) : !olt ? (
        <div className="empty-state">
          {carregando ? "Carregando..." : "Ainda sem dados. O agente envia o status a cada 5 minutos; para ler agora e ver onde a conexão falha, use \"Testar\" no card do equipamento."}
        </div>
      ) : (
        <OltPainel key={olt.ip} olt={olt} licenca={dados?.licenca} />
      )}
    </Modal>
  );
}
