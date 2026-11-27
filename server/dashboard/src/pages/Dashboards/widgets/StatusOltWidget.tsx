import { useState } from "react";
import { ContagemOnus, DadosStatusOlt, OnuPublica, QualidadeSinalOnus, WidgetInstancia } from "../types";
import PieChart, { type FatiaPizza } from "../PieChart";
import { CartaoEquipamento, COR_NIVEL, Linha, ListaEquipamentos, Ponto, Vazio } from "./statusComum";

const LIMITE_PROBLEMAS_INICIAL = 15;

const TEXTO_ESTADO: Record<OnuPublica["estado"], string> = {
  ONLINE: "Online",
  OFFLINE: "Offline",
  FALHA: "Falha na fibra",
  SEM_ENERGIA: "Sem energia",
  DESCONHECIDO: "Desconhecido",
};

const TEXTO_QUALIDADE = { bom: "Bom", atencao: "Atenção", ruim: "Ruim" } as const;

function fmtDbm(v: number): string {
  return `${v.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 2 })} dBm`;
}

// Texto da direita da linha da ONU: o estado quando está fora, o sinal quando está online
function situacaoOnu(o: OnuPublica): string {
  if (o.estado !== "ONLINE") return TEXTO_ESTADO[o.estado];
  if (o.sinal_dbm == null) return "sem leitura de sinal";
  return `${fmtDbm(o.sinal_dbm)} · ${TEXTO_QUALIDADE[o.qualidade ?? "bom"]}`;
}

function LinhaOnu({ o }: { o: OnuPublica }) {
  return (
    <Linha
      nivel={o.nivel}
      nome={o.nome || o.posicao}
      detalhe={o.nome ? o.posicao : null}
      direita={<span style={{ color: o.nivel === "ok" ? "var(--text-secondary)" : COR_NIVEL[o.nivel] }}>{situacaoOnu(o)}</span>}
    />
  );
}

function Pizza({ titulo, fatias }: { titulo: string; fatias: FatiaPizza[] }) {
  const total = fatias.reduce((a, f) => a + f.valor, 0);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, flex: "1 1 200px", minWidth: 0 }}>
      <PieChart fatias={fatias} tamanho={84} rotuloCentro={String(total)} />
      <div style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0, flex: 1 }}>
        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{titulo}</span>
        {fatias.map((f) => (
          <div key={f.rotulo} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11 }}>
            <span aria-hidden style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: f.cor, flexShrink: 0 }} />
            <span style={{ color: "var(--text-secondary)", flex: 1, minWidth: 0 }}>{f.rotulo}</span>
            <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{f.valor}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function fatiasSituacao(t: ContagemOnus): FatiaPizza[] {
  return [
    { rotulo: "Online", valor: t.online, cor: "var(--ok)" },
    { rotulo: "Sem energia", valor: t.sem_energia, cor: "var(--warn)" },
    { rotulo: "Offline ou falha", valor: t.offline + t.falha, cor: "var(--err)" },
  ];
}

function fatiasQualidade(q: QualidadeSinalOnus): FatiaPizza[] {
  const fatias = [
    { rotulo: "Bom (acima de -25,5)", valor: q.bom, cor: "var(--ok)" },
    { rotulo: "Atenção (-25,5 a -27)", valor: q.atencao, cor: "var(--warn)" },
    { rotulo: "Ruim (-27 ou menos)", valor: q.ruim, cor: "var(--err)" },
  ];
  if (q.sem_leitura) fatias.push({ rotulo: "Sem leitura", valor: q.sem_leitura, cor: "var(--text-muted)" });
  return fatias;
}

const estiloBotao = {
  alignSelf: "flex-start",
  background: "none",
  border: "1px solid var(--border)",
  borderRadius: 4,
  color: "var(--text-secondary)",
  fontSize: 11,
  padding: "2px 8px",
  cursor: "pointer",
} as const;

function OnusDaOlt({
  onus,
  totalLista,
  mostrarProblemas,
  mostrarTodas,
}: {
  onus: OnuPublica[];
  totalLista: number;
  mostrarProblemas: boolean;
  mostrarTodas: boolean;
}) {
  const [verMaisProblemas, setVerMaisProblemas] = useState(false);
  const [abrirTodas, setAbrirTodas] = useState(false);
  const problemas = onus.filter((o) => o.nivel !== "ok");
  const problemasVisiveis = verMaisProblemas ? problemas : problemas.slice(0, LIMITE_PROBLEMAS_INICIAL);

  return (
    <>
      {mostrarProblemas && problemas.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>ONUs com problema ({problemas.length}):</span>
          {problemasVisiveis.map((o) => (
            <LinhaOnu key={o.posicao} o={o} />
          ))}
          {problemas.length > LIMITE_PROBLEMAS_INICIAL && (
            <button type="button" style={estiloBotao} onClick={() => setVerMaisProblemas((v) => !v)}>
              {verMaisProblemas ? "Mostrar menos" : `Mostrar mais ${problemas.length - LIMITE_PROBLEMAS_INICIAL}`}
            </button>
          )}
        </div>
      )}
      {mostrarTodas && onus.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <button type="button" style={estiloBotao} aria-expanded={abrirTodas} onClick={() => setAbrirTodas((v) => !v)}>
            {abrirTodas ? "Esconder a lista de ONUs" : `Ver todas as ONUs (${totalLista})`}
          </button>
          {abrirTodas && (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                <thead>
                  <tr style={{ color: "var(--text-muted)", textAlign: "left" }}>
                    <th style={{ padding: "2px 6px 2px 0", fontWeight: 500 }}>Posição</th>
                    <th style={{ padding: "2px 6px", fontWeight: 500 }}>Nome</th>
                    <th style={{ padding: "2px 6px", fontWeight: 500 }}>Situação</th>
                    <th style={{ padding: "2px 0 2px 6px", fontWeight: 500, textAlign: "right" }}>Sinal</th>
                  </tr>
                </thead>
                <tbody>
                  {onus.map((o) => (
                    <tr key={o.posicao} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ padding: "2px 6px 2px 0", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>{o.posicao}</td>
                      <td style={{ padding: "2px 6px", color: "var(--text-primary)", overflowWrap: "anywhere" }}>{o.nome || "—"}</td>
                      <td style={{ padding: "2px 6px", whiteSpace: "nowrap" }}>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 5, color: "var(--text-secondary)" }}>
                          <Ponto nivel={o.nivel} />
                          {o.estado === "ONLINE" && o.qualidade ? TEXTO_QUALIDADE[o.qualidade] : TEXTO_ESTADO[o.estado]}
                        </span>
                      </td>
                      <td style={{ padding: "2px 0 2px 6px", textAlign: "right", whiteSpace: "nowrap", color: "var(--text-primary)" }}>
                        {o.sinal_dbm != null ? fmtDbm(o.sinal_dbm) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {totalLista > onus.length && (
                <div style={{ fontSize: 11, color: "var(--text-muted)", paddingTop: 4 }}>
                  Mostrando {onus.length} de {totalLista} ONUs.
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </>
  );
}

interface Props {
  dados: DadosStatusOlt;
  widget: WidgetInstancia;
}

// A licença é só data ("2026-11-18"), sem hora nem fuso: formata sem passar por Date
function fmtDay(iso: string): string {
  const [a, m, d] = iso.split("-");
  return a && m && d ? `${d}/${m}/${a}` : iso;
}

function partesFora(c: ContagemOnus): string {
  const partes: string[] = [];
  if (c.offline) partes.push(`${c.offline} offline`);
  if (c.falha) partes.push(`${c.falha} em falha`);
  if (c.sem_energia) partes.push(`${c.sem_energia} sem energia`);
  if (c.sinal_ruim) partes.push(`${c.sinal_ruim} sinal ruim`);
  return partes.join(" · ");
}

export default function StatusOltWidget({ dados }: Props) {
  if (!dados.equipamentos || dados.equipamentos.length === 0) {
    return <Vazio texto="Nenhuma OLT cadastrada." />;
  }
  const mostrarGraficos = dados.mostrar_graficos ?? true;
  const mostrarProblemas = dados.mostrar_onus_problema ?? true;
  const mostrarTodas = dados.mostrar_todas_onus ?? true;

  return (
    <ListaEquipamentos>
      {dados.equipamentos.map((eq) => {
        const lic = eq.licenca;
        let textoLicenca: string | null = null;
        if (lic) {
          textoLicenca =
            lic.dias_restantes < 0
              ? `Licença da UNM2000 vencida desde ${fmtDay(lic.fim)}`
              : lic.dias_restantes === 0
              ? "Licença da UNM2000 vence hoje"
              : `Licença da UNM2000 vence em ${lic.dias_restantes} dia(s) (${fmtDay(lic.fim)})`;
        }
        return (
          <CartaoEquipamento key={eq.id} eq={eq}>
            {lic && textoLicenca && (
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: lic.nivel === "ok" ? "var(--text-secondary)" : COR_NIVEL[lic.nivel] }}>
                <Ponto nivel={lic.nivel} />
                {textoLicenca}
              </div>
            )}
            {eq.olts.length === 0 && !eq.sem_status && (
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Nenhuma OLT na última leitura.</div>
            )}
            {eq.olts.map((o, i) => {
              const t = o.totais;
              const onlinePct = t.total > 0 ? (t.online / t.total) * 100 : 0;
              const foraPct = t.total > 0 ? ((t.offline + t.falha + t.sem_energia) / t.total) * 100 : 0;
              const fora = partesFora(t);
              const detalhe = [o.fabricante, o.modelo, o.temperatura != null ? `${Math.round(o.temperatura)} °C` : null]
                .filter(Boolean)
                .join(" · ");
              return (
                <div
                  key={`${o.nome}-${i}`}
                  style={{ display: "flex", flexDirection: "column", gap: 4, paddingTop: i > 0 ? 6 : 0, borderTop: i > 0 ? "1px solid var(--border)" : undefined }}
                >
                  <Linha
                    nivel={o.nivel}
                    nome={o.nome}
                    detalhe={detalhe || null}
                    direita={
                      o.falha_leitura ? (
                        <span style={{ color: "var(--err)" }}>sem leitura</span>
                      ) : (
                        <span style={{ color: COR_NIVEL[o.nivel], fontWeight: 600 }}>
                          {t.online}/{t.total} ONUs online
                        </span>
                      )
                    }
                  />
                  {!o.falha_leitura && t.total > 0 && (
                    <div style={{ width: "100%", height: 4, backgroundColor: "var(--border)", borderRadius: 2, overflow: "hidden", display: "flex" }}>
                      <div style={{ width: `${onlinePct}%`, backgroundColor: "var(--ok)" }} />
                      <div style={{ width: `${foraPct}%`, backgroundColor: o.nivel === "critico" ? "var(--err)" : "var(--warn)" }} />
                    </div>
                  )}
                  {!o.falha_leitura && fora && (
                    <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                      {fora}
                      {o.percentual_fora > 0 && ` (${o.percentual_fora.toLocaleString("pt-BR")}% fora)`}
                    </div>
                  )}
                  {mostrarGraficos && !o.falha_leitura && t.total > 0 && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 12, padding: "4px 0" }}>
                      <Pizza titulo="Situação das ONUs" fatias={fatiasSituacao(t)} />
                      {o.qualidade && o.qualidade.bom + o.qualidade.atencao + o.qualidade.ruim + o.qualidade.sem_leitura > 0 && (
                        <Pizza titulo="Sinal das ONUs online (dBm)" fatias={fatiasQualidade(o.qualidade)} />
                      )}
                    </div>
                  )}
                  {!o.falha_leitura && o.onus && o.onus.length > 0 && (
                    <OnusDaOlt
                      onus={o.onus}
                      totalLista={o.onus_total_lista ?? o.onus.length}
                      mostrarProblemas={mostrarProblemas}
                      mostrarTodas={mostrarTodas}
                    />
                  )}
                  {o.pons.length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 1, paddingLeft: 14 }}>
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>PONs com problema:</span>
                      {o.pons.map((p) => (
                        <span key={`${p.slot}/${p.pon}`} style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                          {p.slot}/{p.pon} · {partesFora(p)}
                        </span>
                      ))}
                      {o.pons_com_problema > o.pons.length && (
                        <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                          e mais {o.pons_com_problema - o.pons.length} PON(s)
                        </span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </CartaoEquipamento>
        );
      })}
    </ListaEquipamentos>
  );
}
