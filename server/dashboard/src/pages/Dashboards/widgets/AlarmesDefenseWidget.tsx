import { DadosAlarmesDefense, WidgetInstancia } from "../types";
import { CartaoEquipamento, COR_NIVEL, Linha, ListaEquipamentos, Vazio } from "./statusComum";

interface Props {
  dados: DadosAlarmesDefense;
  widget: WidgetInstancia;
}

export default function AlarmesDefenseWidget({ dados }: Props) {
  if (!dados.equipamentos || dados.equipamentos.length === 0) {
    return <Vazio texto="Nenhum Defense cadastrado." />;
  }

  return (
    <ListaEquipamentos>
      {dados.equipamentos.map((eq) => {
        const disparos = eq.centrais.reduce((s, c) => s + c.disparos, 0);
        return (
          <CartaoEquipamento
            key={eq.id}
            eq={eq}
            aviso={eq.falha_leitura ? "Não foi possível ler o Defense na última tentativa." : null}
            resumo={
              disparos > 0 && (
                <span style={{ fontSize: 12, fontWeight: 700, color: "var(--err)", whiteSpace: "nowrap" }}>
                  {disparos} em disparo
                </span>
              )
            }
          >
            {eq.centrais.length === 0 && !eq.sem_status && (
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Nenhuma central de alarme.</div>
            )}
            {eq.centrais.map((c, i) => (
              <div key={`${c.nome}-${i}`} style={{ display: "flex", flexDirection: "column", gap: 1 }}>
                <Linha
                  nivel={c.nivel}
                  nome={c.nome}
                  detalhe={c.modelo}
                  direita={
                    <span style={{ color: COR_NIVEL[c.nivel], fontWeight: c.nivel === "ok" ? 400 : 600 }}>
                      {c.disparos > 0 ? "DISPARO" : c.conectada ? "conectada" : "desconectada"}
                    </span>
                  }
                />
                {c.particoes.map((p, j) => {
                  // Desarmada é estado normal (cinza); no link público o servidor nem manda `armada`
                  const texto = p.disparada ? "em disparo" : p.armada === undefined ? null : p.armada ? "armada" : "desarmada";
                  if (!texto) return null;
                  const cor = p.disparada ? "var(--err)" : p.armada ? "var(--ok)" : "var(--text-muted)";
                  return (
                    <div
                      key={`${p.nome}-${j}`}
                      style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 11, paddingLeft: 16 }}
                    >
                      <span style={{ color: "var(--text-secondary)", overflowWrap: "anywhere" }}>{p.nome}</span>
                      <span style={{ color: cor, fontWeight: p.disparada ? 600 : 400, whiteSpace: "nowrap" }}>{texto}</span>
                    </div>
                  );
                })}
              </div>
            ))}
            {eq.incendio.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 1, marginTop: 2 }}>
                <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Centrais de incêndio</span>
                {eq.incendio.map((f, i) => (
                  <span key={`${f.nome}-${i}`} style={{ fontSize: 11, color: "var(--text-secondary)", paddingLeft: 16 }}>
                    {f.nome}
                    {f.modelo && <span style={{ color: "var(--text-muted)" }}> · {f.modelo}</span>}
                  </span>
                ))}
              </div>
            )}
          </CartaoEquipamento>
        );
      })}
    </ListaEquipamentos>
  );
}
