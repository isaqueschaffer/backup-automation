import { ContagemOnus, DadosStatusOlt, WidgetInstancia } from "../types";
import { CartaoEquipamento, COR_NIVEL, Linha, ListaEquipamentos, Ponto, Vazio } from "./statusComum";

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
