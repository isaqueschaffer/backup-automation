import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertCircle,
  Archive,
  Check,
  CheckCircle,
  RotateCcw,
  Search,
  Server,
  SlidersHorizontal,
  Users,
} from "lucide-react";
import { fetchMachines, fetchStats } from "../../api/client";
import { Machine, Stats } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Span, useOverviewLayout } from "./layout";
import MachineHealthCard from "./MachineHealthCard";

export default function Overview() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [editing, setEditing] = useState(false);
  const [showPicker, setShowPicker] = useState(false);
  const [searchPicker, setSearchPicker] = useState("");
  const [now, setNow] = useState(Date.now());
  const [serverSkewMs, setServerSkewMs] = useState(0);

  // Arrastar e soltar dos cards
  const [dragId, setDragId] = useState<string | null>(null);
  const [dropAt, setDropAt] = useState<{ targetId: string; before: boolean } | null>(null);
  const handleArmed = useRef(false);

  const navigate = useNavigate();
  const { toast } = useToast();

  const layout = useOverviewLayout(machines);

  useEffect(() => {
    let cancelled = false;

    const carregar = (silencioso: boolean) => {
      fetchStats()
        .then((s) => {
          if (!cancelled) setStats(s);
        })
        .catch(() => {
          if (!cancelled && !silencioso) toast("Erro ao carregar estatísticas.", "error");
        });

      fetchMachines()
        .then((m) => {
          if (!cancelled) {
            setMachines(m);
            const firstWithTime = m.find(x => x.current_server_time);
            if (firstWithTime?.current_server_time) {
              setServerSkewMs(new Date(firstWithTime.current_server_time).getTime() - Date.now());
            }
          }
        })
        .catch(() => {
          if (!cancelled && !silencioso) {
            setLoadError(true);
            toast("Erro ao carregar máquinas.", "error");
          }
        });
    };

    carregar(false);
    const pollInterval = setInterval(() => carregar(true), 10000);
    const clockInterval = setInterval(() => {
      if (!cancelled) setNow(Date.now());
    }, 1000);

    return () => {
      cancelled = true;
      clearInterval(pollInterval);
      clearInterval(clockInterval);
    };
  }, [toast]);

  const nowMs = now + serverSkewMs;

  const onDragStart = (e: React.DragEvent, id: string) => {
    if (!editing || !handleArmed.current) {
      e.preventDefault();
      return;
    }
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", id);
    setDragId(id);
  };

  const onDragOver = (e: React.DragEvent<HTMLDivElement>, id: string, span: Span) => {
    if (!dragId) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    const rect = e.currentTarget.getBoundingClientRect();
    let before: boolean;
    if (span === 12) {
      before = e.clientY < rect.top + rect.height / 2;
    } else {
      before = e.clientX < rect.left + rect.width / 2;
    }
    if (!dropAt || dropAt.targetId !== id || dropAt.before !== before) {
      setDropAt({ targetId: id, before });
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (dragId && dropAt && dropAt.targetId && dragId !== dropAt.targetId) {
      layout.move(dragId, dropAt.targetId, dropAt.before);
    }
    setDragId(null);
    setDropAt(null);
    handleArmed.current = false;
  };

  const onDragEnd = () => {
    setDragId(null);
    setDropAt(null);
    handleArmed.current = false;
  };

  const filteredPickerMachines = useMemo(() => {
    const term = searchPicker.trim().toLowerCase();
    return [...layout.all]
      .filter(m => {
        if (!term) return true;
        const cName = (m.customer_name || "Sem cliente").toLowerCase();
        const mName = m.name.toLowerCase();
        return cName.includes(term) || mName.includes(term);
      })
      .sort((a, b) => {
        const cA = a.customer_name || "Sem cliente";
        const cB = b.customer_name || "Sem cliente";
        const comp = cA.localeCompare(cB);
        if (comp !== 0) return comp;
        return a.name.localeCompare(b.name);
      });
  }, [layout.all, searchPicker]);

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Visão Geral</h1>
          <p className="page-subtitle">Status em tempo real de todas as máquinas</p>
        </div>
        <div className="flex gap-2">
          <button
            className={editing ? "btn btn-primary" : "btn btn-secondary"}
            onClick={() => setEditing(!editing)}
          >
            {editing ? (
              <>
                <Check size={15} /> Concluir
              </>
            ) : (
              <>
                <SlidersHorizontal size={15} /> Personalizar
              </>
            )}
          </button>
          <button className="btn btn-secondary" onClick={() => navigate("/clientes")}>
            <Users size={15} /> Clientes
          </button>
          <button className="btn btn-primary" onClick={() => navigate("/maquinas")}>
            <Server size={15} /> Máquinas
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="stats-grid">
        <div className="stat-card purple" style={{ cursor: "pointer" }} onClick={() => navigate("/clientes")}>
          <div className="stat-label">Clientes</div>
          <div className="stat-value purple">{stats?.customers_total ?? "—"}</div>
          <Users size={28} className="stat-icon" color="var(--accent)" />
        </div>
        <div className="stat-card cyan" style={{ cursor: "pointer" }} onClick={() => navigate("/maquinas")}>
          <div className="stat-label">Máquinas ativas / total</div>
          <div className="stat-value cyan">
            {stats ? `${stats.machines_active}/${stats.machines_total}` : "—"}
          </div>
          <CheckCircle size={28} className="stat-icon" color="var(--cyan)" />
        </div>
        <div className="stat-card green">
          <div className="stat-label">Backups OK Hoje</div>
          <div className="stat-value green">{stats?.backups_ok ?? "—"}</div>
          <Archive size={28} className="stat-icon" color="var(--ok)" />
        </div>
        <div className="stat-card red">
          <div className="stat-label">Erros Hoje</div>
          <div className="stat-value red">{stats?.backups_error ?? "—"}</div>
          <AlertCircle size={28} className="stat-icon" color="var(--err)" />
        </div>
      </div>

      {/* Barra do modo edição */}
      {editing && (
        <>
          <div
            className="card"
            style={{
              padding: "14px 16px",
              display: "flex",
              flexWrap: "wrap",
              gap: 12,
              alignItems: "center",
              marginBottom: 16,
            }}
          >
            <span>
              {`${layout.visible.length} de ${layout.all.length} máquinas exibidas`}
            </span>
            <button
              className="btn btn-secondary"
              onClick={() => setShowPicker(!showPicker)}
            >
              Escolher máquinas
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => {
                if (confirm("Restaurar a ordem, as larguras e mostrar todas as máquinas?")) {
                  layout.reset();
                }
              }}
            >
              <RotateCcw size={14} /> Restaurar padrão
            </button>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Arraste pela alça para reordenar e escolha a largura de cada card.
            </span>
          </div>

          {/* Painel Escolher máquinas */}
          {showPicker && (
            <div
              className="card"
              style={{
                padding: 16,
                maxHeight: 320,
                overflowY: "auto",
                marginBottom: 16,
              }}
            >
              <div style={{ position: "relative", marginBottom: 12 }}>
                <Search
                  size={14}
                  style={{
                    position: "absolute",
                    left: 12,
                    top: "50%",
                    transform: "translateY(-50%)",
                    color: "var(--text-muted)",
                  }}
                />
                <input
                  type="text"
                  className="form-input"
                  placeholder="Buscar cliente ou máquina..."
                  value={searchPicker}
                  onChange={(e) => setSearchPicker(e.target.value)}
                  style={{ paddingLeft: 34 }}
                />
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {filteredPickerMachines.map(m => {
                  const checked = layout.isVisible(m.id);
                  const isOnline = m.active && m.is_online;
                  return (
                    <label
                      key={m.id}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        fontSize: 13,
                        cursor: "pointer",
                        padding: "4px 0",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => {
                          if (e.target.checked) layout.show(m.id);
                          else layout.hide(m.id);
                        }}
                      />
                      <span
                        className={`dot ${isOnline ? "ok" : "err"}`}
                        style={{ flexShrink: 0 }}
                      />
                      <span>
                        <strong>{m.customer_name || "Sem cliente"}</strong> — {m.name}
                      </span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}

      {/* Cards das máquinas */}
      <div className="section-title">
        <Server size={15} /> Máquinas
      </div>

      {machines.length === 0 && loadError ? (
        <div className="empty-state">
          <div>Não foi possível carregar as máquinas.</div>
        </div>
      ) : machines.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🖥️</div>
          <div>Nenhuma máquina cadastrada ainda.</div>
          <button className="btn btn-primary mt-2" onClick={() => navigate("/maquinas")}>
            Cadastrar primeira máquina
          </button>
        </div>
      ) : layout.visible.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🖥️</div>
          <div>Nenhuma máquina selecionada para a visão geral.</div>
          <button
            className="btn btn-secondary mt-2"
            onClick={() => {
              setEditing(true);
              setShowPicker(true);
            }}
          >
            <SlidersHorizontal size={14} /> Personalizar
          </button>
        </div>
      ) : (
        <div className="overview-grid">
          {layout.visible.map((m) => {
            const span = layout.spanOf(m.id);
            const isDragging = dragId === m.id;
            const isTarget = dropAt?.targetId === m.id && dragId !== m.id;

            return (
              <div
                key={m.id}
                className="overview-item"
                style={{
                  gridColumn: `span ${span}`,
                  minWidth: 0,
                  position: "relative",
                  opacity: isDragging ? 0.4 : 1,
                }}
                draggable={editing}
                onMouseDown={(e) => {
                  handleArmed.current = (e.target as HTMLElement).closest("[data-drag-handle]") !== null;
                }}
                onDragStart={(e) => onDragStart(e, m.id)}
                onDragOver={(e) => onDragOver(e, m.id, span)}
                onDrop={onDrop}
                onDragEnd={onDragEnd}
                onClick={() => {
                  if (!editing) navigate(`/maquinas/${m.id}`);
                }}
              >
                {/* Indicador de destino */}
                {isTarget && (
                  span === 12 ? (
                    <div
                      style={{
                        position: "absolute",
                        left: 0,
                        right: 0,
                        top: dropAt.before ? -2 : undefined,
                        bottom: !dropAt.before ? -2 : undefined,
                        height: 3,
                        background: "var(--accent)",
                        borderRadius: 2,
                        zIndex: 10,
                        pointerEvents: "none",
                      }}
                    />
                  ) : (
                    <div
                      style={{
                        position: "absolute",
                        top: 0,
                        bottom: 0,
                        left: dropAt.before ? -2 : undefined,
                        right: !dropAt.before ? -2 : undefined,
                        width: 3,
                        background: "var(--accent)",
                        borderRadius: 2,
                        zIndex: 10,
                        pointerEvents: "none",
                      }}
                    />
                  )
                )}

                <MachineHealthCard
                  machine={m}
                  nowMs={nowMs}
                  span={span}
                  editing={editing}
                  onSpanChange={(s) => layout.setSpan(m.id, s)}
                  onHide={() => layout.hide(m.id)}
                />
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
