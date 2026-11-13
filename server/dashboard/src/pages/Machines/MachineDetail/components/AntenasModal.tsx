import { useCallback, useEffect, useMemo, useState } from "react";
import { Bell, BellOff, Plus, RefreshCw, Trash2 } from "lucide-react";
import api from "../../../../api/client";
import { AntenaCadastro, AntenaDescoberta, AntenaStatus, AntenaStatusResponse, NVR, SituacaoAntena } from "../../../../api/types";
import Modal from "../../../../components/Modal";
import { useToast } from "../../../../components/Toast";
import { useConfirm } from "../../../../components/ConfirmDialog";
import { useSomenteLeitura } from "../../../../contexts/AuthContext";
import { fmtDate } from "../../../../utils/date";

const ATUALIZAR_A_CADA_MS = 60_000;
const TOLERANCIA_MAC = 32;

// '9c2b.a671.6acf' / '9C-2B-...' / '9c2ba6716acf' -> '9C:2B:A6:71:6A:CF'; "" se não for um MAC
export function normalizarMac(texto: string): string {
  const puro = texto.replace(/[^0-9a-fA-F]/g, "").toUpperCase();
  if (puro.length !== 12 || /[^0-9A-F]/.test(puro)) return "";
  return puro.match(/.{2}/g)!.join(":");
}

const macProximos = (a: string, b: string) =>
  a.slice(0, 8) === b.slice(0, 8) && Math.abs(parseInt(a.replace(/:/g, ""), 16) - parseInt(b.replace(/:/g, ""), 16)) <= TOLERANCIA_MAC;

const SITUACAO: Record<SituacaoAntena | "AGUARDANDO", { rotulo: string; cor: string }> = {
  ONLINE: { rotulo: "Online", cor: "var(--ok)" },
  OFFLINE: { rotulo: "Offline", cor: "var(--err)" },
  SEM_REGISTRO: { rotulo: "Não encontrada", cor: "var(--warn)" },
  ERRO: { rotulo: "Erro no cadastro", cor: "var(--err)" },
  AGUARDANDO: { rotulo: "Aguardando coleta", cor: "var(--text-muted)" },
};

const FONTES: Record<string, string> = { vizinho: "vizinho", arp: "ARP", dhcp: "DHCP", bridge: "bridge" };

// Marcas disponíveis por enquanto (para incluir outra: aqui e em _MARCAS de agent/src/mikrotik/antenas.py)
const MARCAS = ["Ruijie", "Aruba", "Xixian"];

// Marcas do seletor; uma marca já gravada que não está na lista continua aparecendo (não some do cadastro)
const opcoesDeMarca = (atual: string) => (atual && !MARCAS.includes(atual) ? [...MARCAS, atual] : MARCAS);

// Marca da antena: o LLDP/vizinho a detecta quando anuncia; senão o usuário escolhe aqui (grava ao escolher)
function CampoMarca({ valor, detectada, desabilitado, onSalvar }: {
  valor: string; detectada?: string; desabilitado?: boolean; onSalvar: (marca: string) => void;
}) {
  return (
    <select className="form-input" value={valor} disabled={desabilitado} onChange={e => onSalvar(e.target.value)}
      title={detectada ? `O LLDP/vizinho anunciou: ${detectada}. Escolha outra para sobrescrever.` : "O LLDP não identificou a marca: escolha aqui."}
      style={{ width: 150, padding: "3px 8px", fontSize: 12 }}>
      <option value="">{detectada ? `${detectada} (detectada)` : "Escolher a marca"}</option>
      {opcoesDeMarca(valor).map(m => <option key={m} value={m}>{m}</option>)}
    </select>
  );
}

function Selo({ situacao }: { situacao: SituacaoAntena | "AGUARDANDO" }) {
  const { rotulo, cor } = SITUACAO[situacao];
  return (
    <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 999, color: cor, border: `1px solid ${cor}`, whiteSpace: "nowrap" }}>
      {rotulo}
    </span>
  );
}

const mensagemApi = (e: unknown, padrao: string) => {
  const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : padrao;
};

// Antenas de um equipamento ANTENA: status lido pelo MikroTik (via agente), busca automática e cadastro pelo MAC
export default function AntenasModal({ machineId, eq, onAlterado, onClose }: {
  machineId: string;
  eq: NVR;
  onAlterado: () => void;
  onClose: () => void;
}) {
  const { toast } = useToast();
  const confirmar = useConfirm();
  const somenteLeitura = useSomenteLeitura();
  const [dados, setDados] = useState<AntenaStatusResponse | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState("");
  const [cadastradas, setCadastradas] = useState<AntenaCadastro[]>(eq.config_extra?.antenas || []);
  const [salvando, setSalvando] = useState(false);
  const [nome, setNome] = useState("");
  const [mac, setMac] = useState("");
  const [marca, setMarca] = useState("");

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro("");
    try {
      const res = await api.get<AntenaStatusResponse>(`/machines/${machineId}/equipamentos/${eq.id}/antena-status`);
      setDados(res.data);
    } catch {
      setErro("Não foi possível carregar o status das antenas.");
    } finally {
      setCarregando(false);
    }
  }, [machineId, eq.id]);

  useEffect(() => {
    carregar();
    const t = setInterval(carregar, ATUALIZAR_A_CADA_MS);
    return () => clearInterval(t);
  }, [carregar]);

  // Grava a lista inteira no equipamento (o servidor valida e normaliza os MACs)
  const salvar = async (lista: AntenaCadastro[], sucesso: string): Promise<boolean> => {
    setSalvando(true);
    try {
      await api.put(`/machines/${machineId}/equipamentos/${eq.id}`, { config_extra: { ...(eq.config_extra || {}), antenas: lista } });
      setCadastradas(lista);
      toast(sucesso, "success");
      onAlterado();
      return true;
    } catch (e) {
      toast(mensagemApi(e, "Não foi possível salvar as antenas."), "error");
      return false;
    } finally {
      setSalvando(false);
    }
  };

  const adicionar = async (nomeAntena: string, macTexto: string, marcaAntena = "", limpar = false) => {
    const normalizado = normalizarMac(macTexto);
    if (!normalizado) { toast("MAC inválido. Use o formato 9C:2B:A6:71:6A:CF (12 dígitos hexadecimais).", "error"); return; }
    const parecida = cadastradas.find(a => macProximos(normalizarMac(a.mac), normalizado));
    if (parecida) { toast(`Esse MAC já está coberto pela antena "${parecida.nome}" (até ${TOLERANCIA_MAC} endereços de diferença).`, "error"); return; }
    const ok = await salvar(
      [...cadastradas, {
        nome: nomeAntena.trim() || `Antena ${normalizado.slice(-5)}`, mac: normalizado, notificar: true,
        ...(marcaAntena.trim() ? { marca: marcaAntena.trim() } : {}),
      }],
      "Antena cadastrada. O status aparece na próxima leitura do agente (até 3 minutos).",
    );
    if (ok && limpar) { setNome(""); setMac(""); setMarca(""); }
  };

  const remover = async (a: AntenaCadastro) => {
    if (!(await confirmar({
      title: "Remover antena", message: `Remover a antena "${a.nome}" (${a.mac}) do monitoramento?`, confirmLabel: "Remover", variant: "danger",
    }))) return;
    await salvar(cadastradas.filter(x => x.mac !== a.mac), "Antena removida.");
  };

  const definirMarca = (a: AntenaCadastro, nova: string) =>
    salvar(cadastradas.map(x => {
      if (x.mac !== a.mac) return x;
      const { marca: _antiga, ...resto } = x;
      return nova ? { ...resto, marca: nova } : resto;
    }), nova ? `Marca da antena "${a.nome}": ${nova}.` : `Marca da antena "${a.nome}" removida.`);

  const alternarNotificacao = (a: AntenaCadastro) =>
    salvar(cadastradas.map(x => (x.mac === a.mac ? { ...x, notificar: x.notificar === false } : x)),
      a.notificar === false ? "Aviso de antena offline ligado." : "Aviso de antena offline desligado.");

  const statusPorMac = useMemo(() => new Map((dados?.antenas || []).map(s => [s.mac, s])), [dados]);
  const linhas = cadastradas.map(c => ({ cad: c, st: statusPorMac.get(c.mac) as AntenaStatus | undefined }));
  const descobertas: AntenaDescoberta[] = (dados?.descobertas || []).filter(d => !cadastradas.some(c => macProximos(normalizarMac(c.mac), d.mac)));
  const online = linhas.filter(l => l.st?.status === "ONLINE").length;

  return (
    <Modal wide={true} title={`Antenas — ${eq.name}`} onClose={onClose}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
        {dados?.atualizado_em && (
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            Coletado em {fmtDate(dados.atualizado_em)}
            {dados.mikrotik?.identidade ? ` · MikroTik ${dados.mikrotik.identidade}` : ""}
            {linhas.length > 0 ? ` · ${online} de ${linhas.length} online` : ""}
          </span>
        )}
        <button className="btn btn-secondary btn-sm" style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}
          onClick={carregar} disabled={carregando}>
          <RefreshCw size={13} /> Atualizar
        </button>
      </div>

      {erro && <div className="empty-state" style={{ color: "var(--err)" }}>{erro}</div>}
      {dados?.erro && (
        <div style={{ color: "var(--err)", fontSize: 13, marginBottom: 12 }}>
          O agente não conseguiu ler o MikroTik: {dados.erro} (os dados abaixo são da última leitura boa).
        </div>
      )}
      {!erro && !dados?.atualizado_em && !carregando && (
        <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
          Ainda sem leitura. O agente consulta o MikroTik a cada 3 minutos; use "Testar" no card para conferir o acesso SSH já agora.
        </div>
      )}

      <div style={{ fontWeight: 600, marginBottom: 6 }}>Antenas cadastradas</div>
      {linhas.length === 0 ? (
        <div className="empty-state" style={{ marginBottom: 16 }}>
          Nenhuma antena cadastrada. Adicione pela busca automática ou pelo MAC, abaixo.
        </div>
      ) : (
        <div className="table-wrap" style={{ marginBottom: 16 }}>
          <table>
            <thead>
              <tr><th>Antena</th><th>Marca</th><th>Status</th><th>IP</th><th>MAC</th><th>Ping</th><th>Online / offline</th>{!somenteLeitura && <th></th>}</tr>
            </thead>
            <tbody>
              {linhas.map(({ cad, st }) => (
                <tr key={cad.mac}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{cad.nome}</div>
                    {st?.hostname && <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{st.hostname}</div>}
                  </td>
                  <td>
                    {somenteLeitura ? (cad.marca || st?.marca_detectada || "—") : (
                      <CampoMarca valor={cad.marca || ""} detectada={st?.marca_detectada} desabilitado={salvando}
                        onSalvar={nova => definirMarca(cad, nova)} />
                    )}
                  </td>
                  <td><Selo situacao={st ? st.status : "AGUARDANDO"} /></td>
                  <td style={{ fontFamily: "monospace" }}>
                    {st?.ip || cad.ip || "—"}
                    {st?.ip_ultimo && <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "inherit" }}>último IP visto</div>}
                  </td>
                  <td style={{ fontFamily: "monospace", fontSize: 12 }}>
                    {cad.mac}
                    {st?.mac_visto && st.mac_visto !== cad.mac && (
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }} title="MAC encontrado no MikroTik (dentro da tolerância de 32 endereços)">
                        visto como {st.mac_visto}
                      </div>
                    )}
                  </td>
                  <td>{st?.ping_ms === null || st?.ping_ms === undefined ? "—" : st.ping_ms === 0 ? "<1 ms" : `${st.ping_ms} ms`}</td>
                  <td style={{ fontSize: 12 }}>
                    {st?.status === "ONLINE" ? (
                      <span style={{ color: "var(--text-muted)" }}>{st.interface ? `em ${st.interface}` : "respondendo"}</span>
                    ) : st?.offline_desde ? (
                      <span title={st.ultimo_online ? `Última vez online: ${fmtDate(st.ultimo_online)}` : undefined}>
                        offline desde {fmtDate(st.offline_desde, { short: true })}
                      </span>
                    ) : "—"}
                  </td>
                  {!somenteLeitura && (
                    <td style={{ whiteSpace: "nowrap" }}>
                      <button className="btn-icon" disabled={salvando} onClick={() => alternarNotificacao(cad)}
                        title={cad.notificar === false ? "Avisar quando esta antena cair (desligado)" : "Avisando quando esta antena cair (clique para desligar)"}
                        style={{ color: cad.notificar === false ? "var(--text-muted)" : "var(--accent)" }}>
                        {cad.notificar === false ? <BellOff size={14} /> : <Bell size={14} />}
                      </button>
                      <button className="btn-icon" disabled={salvando} style={{ color: "var(--err)" }} title="Remover" onClick={() => remover(cad)}>
                        <Trash2 size={14} />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ fontWeight: 600, marginBottom: 6 }}>Busca automática no MikroTik</div>
      {descobertas.length === 0 ? (
        <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}>
          {dados?.atualizado_em
            ? "Nenhuma antena nova encontrada (pontos de acesso vizinhos ou MACs com os prefixos do equipamento). Se a sua não apareceu, adicione pelo MAC."
            : "Disponível depois da primeira leitura do MikroTik."}
        </div>
      ) : (
        <div className="table-wrap" style={{ marginBottom: 16 }}>
          <table>
            <thead><tr><th>Encontrada</th><th>Marca</th><th>IP</th><th>MAC</th><th>Motivo</th>{!somenteLeitura && <th></th>}</tr></thead>
            <tbody>
              {descobertas.map(d => (
                <tr key={d.mac}>
                  <td>{d.hostname || "Sem nome"}{d.interface && <div style={{ fontSize: 11, color: "var(--text-muted)" }}>em {d.interface}</div>}</td>
                  <td style={{ fontSize: 12 }}>{d.marca || <span style={{ color: "var(--text-muted)" }}>não identificada</span>}</td>
                  <td style={{ fontFamily: "monospace" }}>{d.ip || "—"}</td>
                  <td style={{ fontFamily: "monospace", fontSize: 12 }}>
                    {d.mac}
                    {(d.macs?.length || 0) > 1 && <div style={{ fontSize: 11, color: "var(--text-muted)" }}>+{(d.macs?.length || 1) - 1} MAC próximo(s)</div>}
                  </td>
                  <td style={{ fontSize: 12 }}>
                    {d.motivo}
                    {d.fontes && d.fontes.length > 0 && <div style={{ fontSize: 11, color: "var(--text-muted)" }}>via {d.fontes.map(f => FONTES[f] || f).join(", ")}</div>}
                  </td>
                  {!somenteLeitura && (
                    <td>
                      <button className="btn btn-secondary btn-sm" disabled={salvando} style={{ display: "flex", alignItems: "center", gap: 6 }}
                        onClick={() => adicionar(d.hostname || "", d.mac, d.marca || "")}>
                        <Plus size={13} /> Adicionar
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!somenteLeitura && (
        <>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Adicionar pelo MAC</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr auto", gap: 8, alignItems: "end" }}>
            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label">Nome</label>
              <input className="form-input" type="text" placeholder="Antena da recepção" value={nome} onChange={e => setNome(e.target.value)} />
            </div>
            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label">MAC *</label>
              <input className="form-input" type="text" placeholder="9C:2B:A6:71:6A:CF" value={mac} onChange={e => setMac(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") adicionar(nome, mac, marca, true); }} />
            </div>
            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label">Marca <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>(se o LLDP não achar)</span></label>
              <select className="form-input" value={marca} onChange={e => setMarca(e.target.value)}>
                <option value="">Sem marca</option>
                {MARCAS.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <button className="btn btn-primary" disabled={salvando || !mac.trim()} onClick={() => adicionar(nome, mac, marca, true)}
              style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Plus size={14} /> Adicionar
            </button>
          </div>
          <span style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 6, display: "block" }}>
            Aceita 9C:2B:A6:71:6A:CF, 9c2b.a671.6acf e 9c-2b-a6-71-6a-cf. O mesmo aparelho costuma aparecer com MACs diferentes (porta e rádios), então
            vale qualquer MAC até {TOLERANCIA_MAC} endereços de diferença do informado.
          </span>
        </>
      )}
    </Modal>
  );
}
