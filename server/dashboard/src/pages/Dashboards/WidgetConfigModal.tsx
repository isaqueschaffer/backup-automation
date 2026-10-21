import { useMemo, useState } from "react";
import Modal from "../../components/Modal";
import { OpcoesDashboard, WidgetInstancia } from "./types";
import { CampoWidget, definicaoDe } from "./widgets/registry";

interface Props {
  widget: WidgetInstancia;
  opcoes: OpcoesDashboard | null;
  onSalvar: (patch: { titulo: string | null; config: Record<string, unknown> }) => void;
  onClose: () => void;
}

// Modal de configuração individual das propriedades e filtros de um componente
export default function WidgetConfigModal({
  widget,
  opcoes,
  onSalvar,
  onClose,
}: Props) {
  const def = definicaoDe(widget.tipo);
  const rotulo = def?.rotulo || "Componente";

  const [titulo, setTitulo] = useState<string>(widget.titulo ?? "");
  const [config, setConfig] = useState<Record<string, unknown>>(() =>
    structuredClone(widget.config || {})
  );

  const tiposDisponiveis = useMemo(() => {
    if (!opcoes) return [];
    const set = new Set<string>();
    for (const eq of opcoes.equipamentos) {
      if (eq.tipo) set.add(eq.tipo.toUpperCase());
    }
    return Array.from(set).sort();
  }, [opcoes]);

  const equipamentosAgrupados = useMemo(() => {
    if (!opcoes) return [];
    const map = new Map<string, { maquina: string; itens: typeof opcoes.equipamentos }>();
    for (const eq of opcoes.equipamentos) {
      const chave = eq.maquina_id || eq.maquina;
      if (!map.has(chave)) {
        map.set(chave, { maquina: eq.maquina || "Sem máquina", itens: [] });
      }
      map.get(chave)!.itens.push(eq);
    }
    return Array.from(map.values());
  }, [opcoes]);

  const handleAplicar = () => {
    const limpo = titulo.trim();
    onSalvar({
      titulo: limpo.length > 0 ? limpo : null,
      config,
    });
    onClose();
  };

  const alternarItemArray = (chave: string, id: string) => {
    const atual = Array.isArray(config[chave]) ? (config[chave] as string[]) : [];
    const proximo = atual.includes(id)
      ? atual.filter((x) => x !== id)
      : [...atual, id];
    setConfig((c) => ({ ...c, [chave]: proximo }));
  };

  const renderCampo = (campo: CampoWidget) => {
    if (campo.tipo === "maquinas") {
      if (!opcoes) {
        return (
          <div style={{ padding: 14, textAlign: "center" }}>
            <span className="spinner" />
          </div>
        );
      }
      const marcadas = Array.isArray(config[campo.chave])
        ? (config[campo.chave] as string[])
        : [];
      return (
        <div>
          <div
            style={{
              maxHeight: 180,
              overflowY: "auto",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: 8,
              background: "var(--surface)",
            }}
          >
            {opcoes.maquinas.length === 0 ? (
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                Nenhuma máquina cadastrada.
              </span>
            ) : (
              opcoes.maquinas.map((m) => (
                <label
                  key={m.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "4px 0",
                    cursor: "pointer",
                    fontSize: 13,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={marcadas.includes(m.id)}
                    onChange={() => alternarItemArray(campo.chave, m.id)}
                  />
                  <span>{m.nome}</span>
                </label>
              ))
            )}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
            Nenhuma marcada = todas as máquinas do cliente.
          </div>
        </div>
      );
    }

    if (campo.tipo === "equipamentos") {
      if (!opcoes) {
        return (
          <div style={{ padding: 14, textAlign: "center" }}>
            <span className="spinner" />
          </div>
        );
      }
      const marcados = Array.isArray(config[campo.chave])
        ? (config[campo.chave] as string[])
        : [];
      return (
        <div>
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
            {equipamentosAgrupados.length === 0 ? (
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                Nenhum equipamento cadastrado.
              </span>
            ) : (
              equipamentosAgrupados.map((g) => (
                <div key={g.maquina} style={{ marginBottom: 8 }}>
                  <div
                    style={{
                      fontSize: 12,
                      fontWeight: 600,
                      color: "var(--text-secondary)",
                      marginBottom: 4,
                      paddingBottom: 2,
                      borderBottom: "1px solid var(--border)",
                    }}
                  >
                    {g.maquina}
                  </div>
                  {g.itens.map((eq) => (
                    <label
                      key={eq.id}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        padding: "3px 0 3px 8px",
                        cursor: "pointer",
                        fontSize: 13,
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={marcados.includes(eq.id)}
                        onChange={() => alternarItemArray(campo.chave, eq.id)}
                      />
                      <span>
                        {eq.nome}{" "}
                        <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                          ({eq.tipo})
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
              ))
            )}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
            Nenhum marcado = todos os equipamentos com câmeras.
          </div>
        </div>
      );
    }

    if (campo.tipo === "tipos") {
      if (!opcoes) {
        return (
          <div style={{ padding: 14, textAlign: "center" }}>
            <span className="spinner" />
          </div>
        );
      }
      const marcados = Array.isArray(config[campo.chave])
        ? (config[campo.chave] as string[])
        : [];
      return (
        <div>
          <div
            style={{
              maxHeight: 180,
              overflowY: "auto",
              border: "1px solid var(--border)",
              borderRadius: 6,
              padding: 8,
              background: "var(--surface)",
            }}
          >
            {tiposDisponiveis.length === 0 ? (
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                Nenhum tipo disponível.
              </span>
            ) : (
              tiposDisponiveis.map((t) => (
                <label
                  key={t}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "4px 0",
                    cursor: "pointer",
                    fontSize: 13,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={marcados.includes(t)}
                    onChange={() => alternarItemArray(campo.chave, t)}
                  />
                  <span>{t}</span>
                </label>
              ))
            )}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
            Nenhum marcado = todos os tipos.
          </div>
        </div>
      );
    }

    if (campo.tipo === "periodo") {
      const valor = (config[campo.chave] as string) || "";
      return (
        <select
          className="form-input"
          value={valor}
          onChange={(e) =>
            setConfig((c) => ({
              ...c,
              [campo.chave]: e.target.value ? e.target.value : null,
            }))
          }
        >
          <option value="">Usar o filtro geral do dashboard</option>
          <option value="24h">Últimas 24 horas</option>
          <option value="7d">Últimos 7 dias</option>
          <option value="30d">Últimos 30 dias</option>
        </select>
      );
    }

    if (campo.tipo === "opcao") {
      const valor = (config[campo.chave] as string) ?? "";
      return (
        <select
          className="form-input"
          value={valor}
          onChange={(e) =>
            setConfig((c) => ({ ...c, [campo.chave]: e.target.value }))
          }
        >
          {campo.opcoes.map((op) => (
            <option key={op.valor} value={op.valor}>
              {op.rotulo}
            </option>
          ))}
        </select>
      );
    }

    if (campo.tipo === "booleano") {
      return (
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            cursor: "pointer",
            fontSize: 13,
            userSelect: "none",
          }}
        >
          <input
            type="checkbox"
            checked={Boolean(config[campo.chave])}
            onChange={(e) =>
              setConfig((c) => ({ ...c, [campo.chave]: e.target.checked }))
            }
          />
          <span>{campo.rotulo}</span>
        </label>
      );
    }

    if (campo.tipo === "texto") {
      const texto = typeof config[campo.chave] === "string" ? (config[campo.chave] as string) : "";
      return (
        <div>
          <textarea
            className="form-input"
            rows={6}
            maxLength={campo.max}
            value={texto}
            onChange={(e) =>
              setConfig((c) => ({ ...c, [campo.chave]: e.target.value }))
            }
          />
          <div
            style={{
              fontSize: 12,
              color: "var(--text-muted)",
              textAlign: "right",
              marginTop: 4,
            }}
          >
            {texto.length}/{campo.max}
          </div>
        </div>
      );
    }

    return null;
  };

  const campos = def?.campos || [];

  return (
    <Modal title={`Configurar: ${rotulo}`} onClose={onClose} width={560}>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <label
            style={{
              display: "block",
              fontSize: 13,
              fontWeight: 500,
              marginBottom: 6,
              color: "var(--text-secondary)",
            }}
          >
            Título (opcional)
          </label>
          <input
            type="text"
            className="form-input"
            maxLength={80}
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder={rotulo}
          />
        </div>

        {campos.map((campo) => (
          <div key={campo.chave}>
            {campo.tipo !== "booleano" && (
              <label
                style={{
                  display: "block",
                  fontSize: 13,
                  fontWeight: 500,
                  marginBottom: 6,
                  color: "var(--text-secondary)",
                }}
              >
                {campo.rotulo}
              </label>
            )}
            {renderCampo(campo)}
          </div>
        ))}

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 8,
            marginTop: 12,
            paddingTop: 12,
            borderTop: "1px solid var(--border)",
          }}
        >
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancelar
          </button>
          <button type="button" className="btn btn-primary" onClick={handleAplicar}>
            Aplicar
          </button>
        </div>
      </div>
    </Modal>
  );
}
