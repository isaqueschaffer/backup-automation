import { useRef, useState } from "react";
import type { CSSProperties, DragEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronRight, GripVertical, ListOrdered, Plus, UserMinus } from "lucide-react";
import { Customer, CustomerRun, Machine } from "../../../../api/types";
import StatusBadge from "../../../../components/StatusBadge";
import StatusDots, { StatusLegend } from "../../../../components/StatusDots";
import { fmtDate } from "../../../../utils/date";
import { statusTone } from "../../../../utils/statusTone";
import { historicoDaMaquina } from "../runUtils";

// Move o item de `from` para a posição de inserção `insertAt` (0..n, antes do item insertAt)
export function moveItem<T>(list: T[], from: number, insertAt: number): T[] {
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(insertAt > from ? insertAt - 1 : insertAt, 0, item);
  return next;
}

const dropLine: CSSProperties = {
  position: "absolute", left: 8, right: 8, height: 3, borderRadius: 2,
  background: "var(--primary, #6366f1)", boxShadow: "0 0 6px var(--primary, #6366f1)", pointerEvents: "none",
};

// Máquinas e fila de backup do cliente: máquinas na ordem, com arrastar e soltar (HTML5 nativo)
export default function QueueSection({
  customer,
  runs,
  saving,
  onReorder,
  onDetach,
  onAdd,
}: {
  customer: Customer;
  runs?: CustomerRun[] | null;
  saving: boolean;
  onReorder: (from: number, insertAt: number) => void;
  onDetach: (m: Machine) => void;
  onAdd: () => void;
}) {
  const navigate = useNavigate();
  const machines = customer.machines;
  const locked = customer.queue_active;
  const canDrag = !locked && !saving && machines.length > 1;

  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [insertAt, setInsertAt] = useState<number | null>(null);
  // Só a alça inicia o arraste (evita arrastar ao selecionar texto ou clicar no link)
  const handleArmed = useRef(false);

  const resetDrag = () => { setDragIndex(null); setInsertAt(null); handleArmed.current = false; };

  const onDragStart = (e: DragEvent, idx: number) => {
    if (!canDrag || !handleArmed.current) { e.preventDefault(); return; }
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", machines[idx].id); // necessário no Firefox
    setDragIndex(idx);
  };

  const onDragOver = (e: DragEvent<HTMLDivElement>, idx: number) => {
    if (dragIndex === null) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    const rect = e.currentTarget.getBoundingClientRect();
    const pos = e.clientY < rect.top + rect.height / 2 ? idx : idx + 1;
    if (pos !== insertAt) setInsertAt(pos);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    if (dragIndex !== null && insertAt !== null && insertAt !== dragIndex && insertAt !== dragIndex + 1) {
      onReorder(dragIndex, insertAt);
    }
    resetDrag();
  };

  // queue_current_index conta só as máquinas ativas (na ordem da fila), como no servidor
  const currentId = locked && customer.queue_current_index != null
    ? machines.filter(m => m.active)[customer.queue_current_index]?.id ?? null
    : null;

  return (
    <div style={{ marginBottom: 24 }}>
      <div className="flex items-center justify-between mb-3">
        <div className="section-title" style={{ marginBottom: 0 }}>
          <ListOrdered size={15} style={{ flexShrink: 0 }} /> Máquinas e fila de backup
          <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 600, padding: "2px 8px", borderRadius: 999, background: "rgba(255,255,255,0.06)", color: "var(--text-muted)" }}>
            {machines.length} máquina(s)
          </span>
        </div>
        <button className="btn btn-secondary" onClick={onAdd} disabled={locked}
          title={locked ? "Aguarde a fila terminar para alterar as máquinas" : "Adicionar uma máquina sem cliente"}>
          <Plus size={14} style={{ flexShrink: 0 }} /> Adicionar máquina
        </button>
      </div>

      {locked ? (
        <div className="text-sm" style={{ color: "var(--warn)", marginBottom: 10 }}>
          Fila em andamento: a ordem e as máquinas não podem ser alteradas até ela terminar (ou ser parada).
        </div>
      ) : machines.length > 1 && (
        <div className="text-sm text-muted" style={{ marginBottom: 10 }}>
          Arraste pela alça <GripVertical size={12} style={{ verticalAlign: "middle", flexShrink: 0 }} /> para mudar a ordem. As máquinas fazem backup uma por vez, de cima para baixo.
        </div>
      )}

      {Array.isArray(runs) && machines.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <StatusLegend />
        </div>
      )}

      {machines.length === 0 ? (
        <div className="empty-state" style={{ padding: 32 }}>
          <div className="empty-icon">🖥️</div>
          <div>Nenhuma máquina neste cliente.</div>
          <button className="btn btn-primary mt-2" onClick={onAdd}>Adicionar máquina</button>
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: "hidden" }} onDragLeave={e => {
          if (!e.currentTarget.contains(e.relatedTarget as Node)) setInsertAt(null);
        }}>
          {machines.map((m, idx) => {
            const isCurrent = currentId === m.id;
            const isDragged = dragIndex === idx;
            const hist = Array.isArray(runs) ? historicoDaMaquina(runs, m.id) : null;
            const okCount = hist ? hist.filter((item) => statusTone(item.status) === "ok").length : 0;

            return (
              <div key={m.id}
                draggable={canDrag}
                onMouseDown={e => { handleArmed.current = !!(e.target as HTMLElement).closest("[data-drag-handle]"); }}
                onDragStart={e => onDragStart(e, idx)}
                onDragOver={e => onDragOver(e, idx)}
                onDrop={onDrop}
                onDragEnd={resetDrag}
                // Clique na linha abre a máquina (exceto na alça e nos botões/links)
                onClick={e => { if (!(e.target as HTMLElement).closest("button, a, [data-drag-handle]")) navigate(`/maquinas/${m.id}`); }}
                title="Abrir a máquina"
                style={{ cursor: "pointer",
                  position: "relative", display: "flex", alignItems: "center", gap: 14, padding: "12px 16px",
                  borderBottom: idx < machines.length - 1 ? "1px solid var(--border)" : "none",
                  opacity: isDragged ? 0.4 : 1,
                  background: isCurrent ? "rgba(245,158,11,0.10)" : "transparent",
                  borderLeft: isCurrent ? "3px solid var(--warn)" : "3px solid transparent",
                }}>
                {insertAt === idx && <div style={{ ...dropLine, top: -2 }} />}
                {insertAt === idx + 1 && idx === machines.length - 1 && <div style={{ ...dropLine, bottom: -2 }} />}

                <span data-drag-handle
                  title={canDrag ? "Arraste para reordenar" : locked ? "Fila em andamento" : ""}
                  style={{ display: "flex", color: "var(--text-muted)", cursor: canDrag ? "grab" : "not-allowed", opacity: canDrag ? 1 : 0.35 }}>
                  <GripVertical size={16} style={{ flexShrink: 0 }} />
                </span>
                <div style={{ width: 26, height: 26, borderRadius: "50%", background: "rgba(255,255,255,0.06)", border: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, color: "var(--text-muted)", flexShrink: 0 }}>
                  {idx + 1}
                </div>
                <span title={!m.active ? "Desativada" : m.is_online ? "Agente online" : "Agente offline"} style={{
                  width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                  background: !m.active ? "var(--text-muted)" : m.is_online ? "var(--ok)" : "var(--err)",
                  boxShadow: m.active && m.is_online ? "0 0 6px var(--ok)" : "none",
                }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <Link to={`/maquinas/${m.id}`} style={{ fontWeight: 600, fontSize: 14, color: "var(--text-primary)" }}>{m.name}</Link>
                    {isCurrent && <span style={{ fontSize: 11, fontWeight: 700, color: "var(--warn)" }}>● Em backup agora</span>}
                  </div>
                  <div className="text-xs text-muted" style={{ marginTop: 2 }}>
                    {m.nvr_count} equipamento(s) • Último backup: {fmtDate(m.last_backup_at, { empty: "nunca" })}
                  </div>
                </div>
                {hist !== null && (
                  hist.length === 0 ? (
                    <span className="text-xs text-muted">sem rodadas</span>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3, flexShrink: 0 }}>
                      <StatusDots items={hist} />
                      <span className="text-xs text-muted">{okCount}/{hist.length} OK</span>
                    </div>
                  )
                )}
                <StatusBadge status={m.last_backup_status} />
                <Link to={`/maquinas/${m.id}`} className="btn btn-secondary btn-sm" title="Abrir a máquina (equipamentos, galeria, backups)"
                  style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  Abrir <ChevronRight size={13} style={{ flexShrink: 0 }} />
                </Link>
                <button className="btn btn-secondary btn-sm" disabled={locked || saving} onClick={() => onDetach(m)}
                  title={locked ? "Aguarde a fila terminar" : "Tirar esta máquina do cliente (ela continua cadastrada)"}
                  style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--err)" }}>
                  <UserMinus size={13} style={{ flexShrink: 0 }} /> Remover do cliente
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
