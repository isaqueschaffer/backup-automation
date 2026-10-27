import type { Dispatch, SetStateAction } from "react";
import { Check } from "lucide-react";
import { OpcoesDashboard } from "./types";

interface Props {
  config: Record<string, unknown>;
  setConfig: Dispatch<SetStateAction<Record<string, unknown>>>;
  opcoes: OpcoesDashboard | null;
}

interface MetricaDef {
  chave: string;
  rotulo: string;
  grupo: "Gravador" | "Discos (HD)";
}

const METRICAS_CONFIG: MetricaDef[] = [
  { chave: "cpu", rotulo: "CPU", grupo: "Gravador" },
  { chave: "ram", rotulo: "Memória (RAM)", grupo: "Gravador" },
  { chave: "uptime", rotulo: "Tempo ligado", grupo: "Gravador" },
  { chave: "disco_uso", rotulo: "Uso", grupo: "Discos (HD)" },
  { chave: "disco_temperatura", rotulo: "Temperatura", grupo: "Discos (HD)" },
  { chave: "disco_saude", rotulo: "Saúde", grupo: "Discos (HD)" },
  { chave: "disco_capacidade", rotulo: "Capacidade", grupo: "Discos (HD)" },
  { chave: "disco_idade", rotulo: "Idade", grupo: "Discos (HD)" },
];

const TODAS_CHAVES = METRICAS_CONFIG.map((m) => m.chave);
const CHAVES_DISCO = METRICAS_CONFIG.filter((m) => m.grupo === "Discos (HD)").map((m) => m.chave);

// Editor visual de telemetria configurável para gravadores
export default function TelemetriaConfigEditor({ config, setConfig, opcoes }: Props) {
  if (!opcoes) {
    return (
      <div style={{ padding: 14, textAlign: "center" }}>
        <span className="spinner" />
      </div>
    );
  }

  const metricasCfg = Array.isArray(config.metricas) ? (config.metricas as string[]) : [];
  const ativas = new Set<string>(metricasCfg.length > 0 ? metricasCfg : TODAS_CHAVES);

  const definirMetricas = (novas: string[]) => {
    const setNovas = new Set(novas);
    const ordenadas = TODAS_CHAVES.filter((k) => setNovas.has(k));
    const resultado = ordenadas.length === 0 || ordenadas.length === TODAS_CHAVES.length ? [] : ordenadas;
    setConfig((prev) => ({ ...prev, metricas: resultado }));
  };

  const alternarMetrica = (chave: string) => {
    if (ativas.has(chave)) {
      if (ativas.size <= 1) return;
      const proximas = Array.from(ativas).filter((k) => k !== chave);
      definirMetricas(proximas);
    } else {
      const proximas = [...Array.from(ativas), chave];
      definirMetricas(proximas);
    }
  };

  const temDiscoAtivo = CHAVES_DISCO.some((k) => ativas.has(k));

  const eqsFiltro = Array.isArray(config.equipamentos) ? (config.equipamentos as string[]) : [];
  const escopo = opcoes.equipamentos.filter((eq) => {
    const temDiscos = Array.isArray(eq.discos) && eq.discos.length > 0;
    if (!temDiscos) return false;
    if (eqsFiltro.length > 0 && !eqsFiltro.includes(eq.id)) return false;
    return true;
  });

  const discosConfig: Record<string, string[]> =
    typeof config.discos === "object" && config.discos !== null && !Array.isArray(config.discos)
      ? (config.discos as Record<string, string[]>)
      : {};

  const alternarDisco = (eqId: string, nomeDisco: string) => {
    const proximo = { ...discosConfig };
    const atuais = Array.isArray(proximo[eqId]) ? proximo[eqId] : [];
    let novosNomes: string[];
    if (atuais.includes(nomeDisco)) {
      novosNomes = atuais.filter((d) => d !== nomeDisco);
    } else {
      novosNomes = [...atuais, nomeDisco];
    }
    if (novosNomes.length === 0) {
      delete proximo[eqId];
    } else {
      proximo[eqId] = novosNomes;
    }
    setConfig((prev) => ({ ...prev, discos: proximo }));
  };

  const limparDiscos = (eqId: string) => {
    const proximo = { ...discosConfig };
    delete proximo[eqId];
    setConfig((prev) => ({ ...prev, discos: proximo }));
  };

  const rotulosResumo = METRICAS_CONFIG
    .filter((m) => ativas.has(m.chave))
    .map((m) => (m.grupo === "Discos (HD)" ? `${m.rotulo} dos discos` : m.rotulo));

  return (
    <div>
      {/* Atalhos rápidos de métricas */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          flexWrap: "wrap",
          marginBottom: 12,
        }}
      >
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Atalhos:</span>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ padding: "4px 10px", fontSize: 12 }}
          onClick={() => definirMetricas(TODAS_CHAVES)}
        >
          Tudo
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ padding: "4px 10px", fontSize: 12 }}
          onClick={() => definirMetricas(CHAVES_DISCO)}
        >
          Só discos
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ padding: "4px 10px", fontSize: 12 }}
          onClick={() => definirMetricas(["cpu", "ram", "disco_temperatura"])}
        >
          CPU, RAM e temperatura
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ padding: "4px 10px", fontSize: 12 }}
          onClick={() => definirMetricas(["cpu", "ram", "uptime"])}
        >
          Desempenho
        </button>
      </div>

      {/* Grupos de métricas com chips interativos */}
      {(["Gravador", "Discos (HD)"] as const).map((grupo) => {
        const metricasDoGrupo = METRICAS_CONFIG.filter((m) => m.grupo === grupo);
        return (
          <div key={grupo} style={{ marginBottom: 12 }}>
            <div
              style={{
                fontSize: 11,
                fontWeight: 600,
                textTransform: "uppercase",
                color: "var(--text-muted)",
                letterSpacing: "0.4px",
                marginBottom: 6,
              }}
            >
              {grupo}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {metricasDoGrupo.map((m) => {
                const ativa = ativas.has(m.chave);
                const ehUltimaAtiva = ativa && ativas.size <= 1;
                return (
                  <button
                    key={m.chave}
                    type="button"
                    aria-pressed={ativa}
                    onClick={() => {
                      if (!ehUltimaAtiva) alternarMetrica(m.chave);
                    }}
                    style={{
                      borderRadius: 999,
                      padding: "5px 12px",
                      fontSize: 13,
                      cursor: ehUltimaAtiva ? "not-allowed" : "pointer",
                      opacity: ehUltimaAtiva ? 0.6 : 1,
                      border: `1px solid ${ativa ? "var(--primary)" : "var(--border)"}`,
                      backgroundColor: ativa ? "var(--surface-2)" : "var(--surface)",
                      color: ativa ? "var(--primary)" : "var(--text-secondary)",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    {ativa && <Check size={13} style={{ flexShrink: 0 }} />}
                    <span>{m.rotulo}</span>
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}

      {/* Seção de seleção de discos por gravador */}
      {temDiscoAtivo && (
        <div style={{ marginTop: 12 }}>
          <div
            style={{
              fontSize: 11,
              fontWeight: 600,
              textTransform: "uppercase",
              color: "var(--text-muted)",
              letterSpacing: "0.4px",
              marginBottom: 6,
            }}
          >
            Quais discos
          </div>
          <div
            style={{
              maxHeight: 220,
              overflowY: "auto",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: 8,
              background: "var(--surface)",
            }}
          >
            {escopo.length === 0 ? (
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                Os discos aparecem aqui depois que o gravador enviar a telemetria.
              </div>
            ) : (
              escopo.map((eq) => {
                const marcados = Array.isArray(discosConfig[eq.id]) ? discosConfig[eq.id] : [];
                const temMarcados = marcados.length > 0;
                const discosLista = eq.discos || [];

                return (
                  <div
                    key={eq.id}
                    style={{
                      marginBottom: 10,
                      paddingBottom: 8,
                      borderBottom: "1px solid var(--border)",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        marginBottom: 4,
                      }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 600 }}>
                        <span>{eq.nome}</span>
                        <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>
                          {" · "}{eq.maquina}
                        </span>
                      </div>
                      {temMarcados && (
                        <button
                          type="button"
                          className="btn btn-secondary"
                          style={{ padding: "2px 6px", fontSize: 11 }}
                          onClick={() => limparDiscos(eq.id)}
                        >
                          Limpar
                        </button>
                      )}
                    </div>

                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fill, minmax(110px, 1fr))",
                        gap: 4,
                        fontSize: 13,
                      }}
                    >
                      {discosLista.map((nomeDisco) => (
                        <label
                          key={nomeDisco}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 6,
                            cursor: "pointer",
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={marcados.includes(nomeDisco)}
                            onChange={() => alternarDisco(eq.id, nomeDisco)}
                          />
                          <span
                            style={{
                              whiteSpace: "nowrap",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                            }}
                            title={nomeDisco}
                          >
                            {nomeDisco}
                          </span>
                        </label>
                      ))}
                    </div>
                    {!temMarcados && (
                      <div
                        style={{
                          fontSize: 11,
                          color: "var(--text-muted)",
                          marginTop: 2,
                        }}
                      >
                        Nenhum marcado = todos os discos
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* Resumo explicativo */}
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 10 }}>
        Vai exibir: {rotulosResumo.join(", ")}
      </div>
    </div>
  );
}
