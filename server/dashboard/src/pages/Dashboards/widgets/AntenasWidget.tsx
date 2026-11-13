import { fmtOfflineHa } from "../../../utils/date";
import { DadosAntenas, WidgetInstancia } from "../types";
import { CartaoEquipamento, COR_NIVEL, Linha, ListaEquipamentos, Vazio } from "./statusComum";

interface Props {
  dados: DadosAntenas;
  widget: WidgetInstancia;
}

const ROTULO_STATUS: Record<string, string> = {
  OFFLINE: "fora do ar",
  SEM_REGISTRO: "sem registro",
  ERRO: "erro na leitura",
};

export default function AntenasWidget({ dados }: Props) {
  if (!dados.equipamentos || dados.equipamentos.length === 0) {
    return <Vazio texto="Nenhum equipamento de antenas." />;
  }

  return (
    <ListaEquipamentos>
      {dados.equipamentos.map((eq) => {
        const cor =
          eq.total === 0 ? "var(--text-muted)" : eq.online === eq.total ? "var(--ok)" : eq.online === 0 ? "var(--err)" : "var(--warn)";
        return (
          <CartaoEquipamento
            key={eq.id}
            eq={eq}
            aviso={eq.falha_leitura ? "Não foi possível ler o MikroTik na última tentativa; mostrando a leitura anterior." : null}
            resumo={
              eq.total > 0 && (
                <span style={{ fontSize: 12, fontWeight: 700, color: cor, whiteSpace: "nowrap" }}>
                  {eq.online}/{eq.total} online
                </span>
              )
            }
          >
            {eq.antenas.length === 0 ? (
              !eq.sem_status && <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Nenhuma antena cadastrada.</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {eq.antenas.map((a, i) => {
                  let direita: string;
                  if (a.status === "ONLINE") {
                    direita = dados.mostrar_latencia && a.ping_ms != null ? `${Math.round(a.ping_ms)} ms` : "online";
                  } else {
                    const ha = fmtOfflineHa(a.fora_segundos);
                    direita = ha ? `${ROTULO_STATUS[a.status] ?? a.status} ${ha}` : ROTULO_STATUS[a.status] ?? a.status;
                  }
                  return (
                    <Linha
                      key={`${a.nome}-${i}`}
                      nivel={a.nivel}
                      nome={a.nome}
                      detalhe={a.marca}
                      direita={<span style={{ color: a.status === "ONLINE" ? "var(--text-secondary)" : COR_NIVEL[a.nivel] }}>{direita}</span>}
                    />
                  );
                })}
              </div>
            )}
          </CartaoEquipamento>
        );
      })}
    </ListaEquipamentos>
  );
}
