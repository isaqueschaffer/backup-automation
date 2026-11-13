import { useEffect, useMemo, useState } from "react";
import api from "../../api/client";
import { Machine } from "../../api/types";

// Máquinas que um Visualizador / Somente leitura vê. Vazio = todas as da conta (o servidor também entende assim).
export default function MaquinasUsuarioCampo({ contaId, restringir, onRestringir, selecionadas, onSelecionadas }: {
  contaId?: string;
  restringir: boolean;
  onRestringir: (v: boolean) => void;
  selecionadas: string[];
  onSelecionadas: (ids: string[]) => void;
}) {
  const [maquinas, setMaquinas] = useState<Machine[] | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    let cancelado = false;
    const config = contaId ? { headers: { "X-Conta-ID": contaId } } : undefined;
    api.get<Machine[]>("/machines", config)
      .then(r => { if (!cancelado) setMaquinas(r.data); })
      .catch(() => { if (!cancelado) setErro("Não foi possível carregar as máquinas da conta."); });
    return () => { cancelado = true; };
  }, [contaId]);

  // Agrupadas por Cliente (sem cliente por último), em ordem alfabética
  const grupos = useMemo(() => {
    const mapa = new Map<string, Machine[]>();
    for (const m of maquinas || []) {
      const chave = m.customer_name || "";
      mapa.set(chave, [...(mapa.get(chave) || []), m]);
    }
    return [...mapa.entries()]
      .sort(([a], [b]) => (a === "" ? 1 : b === "" ? -1 : a.localeCompare(b, "pt-BR")))
      .map(([cliente, ms]) => ({ cliente, maquinas: ms.sort((a, b) => a.name.localeCompare(b.name, "pt-BR")) }));
  }, [maquinas]);

  const marcadas = new Set(selecionadas);
  const alternar = (id: string) =>
    onSelecionadas(marcadas.has(id) ? selecionadas.filter(x => x !== id) : [...selecionadas, id]);
  const alternarCliente = (ms: Machine[]) => {
    const todas = ms.every(m => marcadas.has(m.id));
    const ids = new Set(selecionadas);
    for (const m of ms) { if (todas) ids.delete(m.id); else ids.add(m.id); }
    onSelecionadas([...ids]);
  };

  return (
    <div className="form-group">
      <label className="form-label">Máquinas que o usuário vê</label>
      <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 8 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
          <input type="radio" checked={!restringir} onChange={() => onRestringir(false)} />
          Todas as máquinas da conta (inclusive as que forem criadas depois)
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
          <input type="radio" checked={restringir} onChange={() => onRestringir(true)} />
          Só as máquinas marcadas
        </label>
      </div>
      {restringir && (
        erro ? <div style={{ fontSize: 12, color: "var(--err)" }}>{erro}</div>
        : !maquinas ? <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Carregando máquinas...</div>
        : maquinas.length === 0 ? <div style={{ fontSize: 12, color: "var(--text-muted)" }}>A conta não tem máquinas.</div>
        : (
          <div style={{ maxHeight: 260, overflowY: "auto", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px" }}>
            {grupos.map(g => {
              const todas = g.maquinas.every(m => marcadas.has(m.id));
              const algumas = !todas && g.maquinas.some(m => marcadas.has(m.id));
              return (
                <div key={g.cliente || "-"} style={{ padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 600, fontSize: 13, cursor: "pointer" }}>
                    <input type="checkbox" checked={todas} ref={el => { if (el) el.indeterminate = algumas; }}
                      onChange={() => alternarCliente(g.maquinas)} />
                    {g.cliente || "Sem cliente"}
                    <span style={{ fontWeight: 400, fontSize: 11, color: "var(--text-muted)" }}>
                      ({g.maquinas.filter(m => marcadas.has(m.id)).length} de {g.maquinas.length})
                    </span>
                  </label>
                  <div style={{ display: "flex", flexDirection: "column", gap: 2, paddingLeft: 24, marginTop: 4 }}>
                    {g.maquinas.map(m => (
                      <label key={m.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
                        <input type="checkbox" checked={marcadas.has(m.id)} onChange={() => alternar(m.id)} />
                        {m.name}
                      </label>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )
      )}
      <div className="text-xs text-muted" style={{ marginTop: 4 }}>
        Com máquinas marcadas, o usuário só vê essas máquinas, os clientes delas e os alertas delas. ZIP do cliente, rodadas
        de backup e dashboard do cliente só aparecem se ele tiver todas as máquinas do cliente. Máquina nova não entra sozinha.
      </div>
    </div>
  );
}
