import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertCircle,
  AlertTriangle,
  Archive,
  Check,
  CheckCircle,
  Clock,
  LayoutGrid,
  List,
  RotateCcw,
  Search,
  Server,
  SlidersHorizontal,
  Users,
} from "lucide-react";
import { fetchMachines, fetchStats } from "../../api/client";
import { Machine, MaquinaSemBackup, Stats } from "../../api/types";
import { useToast } from "../../components/Toast";
import { useConfirm } from "../../components/ConfirmDialog";
import { Span, useOverviewLayout } from "./layout";
import MachineHealthCard from "./MachineHealthCard";
import { useRotulos } from "../../contexts/AuthContext";
import StatusBadge from "../../components/StatusBadge";
import { fmtDate } from "../../utils/date";
import { fmtAtraso, gravidadeDa, useVista } from "./gravidade";

export default function Overview() {
  const { plural, singular, singularMin } = useRotulos();
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
  const confirmar = useConfirm();

  const layout = useOverviewLayout(machines);
  const vista = useVista();

  const semBackup = useMemo(
    () => new Map<string, MaquinaSemBackup>((stats?.sem_backup ?? []).map(s => [s.machine_id, s])),
    [stats],
  );

  // Problemas primeiro (padrão) ou a ordem montada no "Personalizar"; editando, vale sempre a personalizada
  const ordenadas = useMemo(() => {
    if (editing || vista.ordem === "personalizada") return layout.visible;
    return [...layout.visible].sort((a, b) => {
      const d = gravidadeDa(a, semBackup).nivel - gravidadeDa(b, semBackup).nivel;
      if (d !== 0) return d;
      return (a.customer_name || "").localeCompare(b.customer_name || "") || a.name.localeCompare(b.name);
    });
  }, [editing, vista.ordem, layout.visible, semBackup]);
  const modoLista = vista.modo === "lista" && !editing;

  // Números de hoje abrem a lista de backups já filtrada (o dia padrão da lista é hoje)
  const abrirBackups = (status: string) => navigate(`/backups?status=${status}`);
  const abrirMaquina = (id: string) => navigate(`/maquinas/${id}`);
  const semBackupLista = stats?.sem_backup ?? []; // API anterior a 26/11/2026 não manda o campo
  const temSemBackup = semBackupLista.length > 0;

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
        const cName = (m.customer_name || `Sem ${singularMin}`).toLowerCase();
        const mName = m.name.toLowerCase();
        return cName.includes(term) || mName.includes(term);
      })
      .sort((a, b) => {
        const cA = a.customer_name || `Sem ${singularMin}`;
        const cB = b.customer_name || `Sem ${singularMin}`;
        const comp = cA.localeCompare(cB);
        if (comp !== 0) return comp;
        return a.name.localeCompare(b.name);
      });
  }, [layout.all, searchPicker, singularMin]);

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Visão Geral</h1>
          <p className="page-subtitle">Status em tempo real de todas as máquinas</p>
        </div>
        <div className="flex gap-2">
          <button
            className={`${editing ? "btn btn-primary" : "btn btn-secondary"} so-computador`}
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
          <button className="btn btn-secondary so-computador" onClick={() => navigate("/clientes")}>
            <Users size={15} /> {plural}
          </button>
          <button className="btn btn-primary so-computador" onClick={() => navigate("/maquinas")}>
            <Server size={15} /> Máquinas
          </button>
        </div>
      </div>

      {/* Números de hoje (dia de Brasília) */}
      <div className="stats-grid">
        <button type="button" className="stat-card purple" onClick={() => navigate("/clientes")}>
          <div className="stat-label">{plural}</div>
          <div className="stat-value purple">{stats?.customers_total ?? "—"}</div>
          <Users size={28} className="stat-icon" color="var(--accent)" />
        </button>
        <button
          type="button"
          className="stat-card cyan"
          onClick={() => navigate("/maquinas")}
          title={stats ? `${stats.machines_online} online de ${stats.machines_active} ativas (${stats.machines_total} no total)` : undefined}
        >
          <div className="stat-label">Máquinas online</div>
          <div className="stat-value cyan">
            {stats ? `${stats.machines_online ?? "—"}/${stats.machines_active}` : "—"}
          </div>
          <CheckCircle size={28} className="stat-icon" color="var(--cyan)" />
        </button>
        <button type="button" className="stat-card green" onClick={() => abrirBackups("OK")}>
          <div className="stat-label">Backups OK hoje</div>
          <div className="stat-value green">{stats?.backups_ok ?? "—"}</div>
          <Archive size={28} className="stat-icon" color="var(--ok)" />
        </button>
        <button type="button" className="stat-card amber" onClick={() => abrirBackups("PARTIAL")}>
          <div className="stat-label">Parciais hoje</div>
          <div className="stat-value amber">{stats ? (stats.backups_partial ?? "—") : "—"}</div>
          <AlertTriangle size={28} className="stat-icon" color="var(--warn)" />
        </button>
        <button type="button" className="stat-card red" onClick={() => abrirBackups("ERROR")}>
          <div className="stat-label">Erros hoje</div>
          <div className="stat-value red">{stats?.backups_error ?? "—"}</div>
          <AlertCircle size={28} className="stat-icon" color="var(--err)" />
        </button>
        <button
          type="button"
          className={`stat-card ${temSemBackup ? "red" : "green"}`}
          onClick={() => document.getElementById("sem-backup")?.scrollIntoView({ behavior: "smooth", block: "start" })}
          disabled={!temSemBackup}
          title="Máquinas que não fizeram o backup do último horário agendado"
        >
          <div className="stat-label">Sem backup</div>
          <div className={`stat-value ${temSemBackup ? "red" : "green"}`}>
            {stats ? semBackupLista.length : "—"}
          </div>
          <Clock size={28} className="stat-icon" color={temSemBackup ? "var(--err)" : "var(--ok)"} />
        </button>
      </div>

      {/* Esperado × realizado: máquinas que não fizeram o backup do último horário agendado */}
      {stats && temSemBackup && (
        <div id="sem-backup" className="card sem-backup-card">
          <div className="section-title" style={{ marginBottom: 10 }}>
            <Clock size={15} /> Sem backup desde o horário agendado ({semBackupLista.length})
          </div>
          <div className="table-wrap">
            <table className="tabela-cartoes">
              <thead>
                <tr>
                  <th>Máquina</th>
                  <th>{singular}</th>
                  <th>Horário perdido</th>
                  <th>Atraso</th>
                  <th>Último backup</th>
                  <th>Comunicação</th>
                </tr>
              </thead>
              <tbody>
                {semBackupLista.map(item => (
                  <tr key={item.machine_id} className="linha-clicavel" onClick={() => abrirMaquina(item.machine_id)}>
                    <td data-label="">
                      <button
                        type="button"
                        className="link-botao"
                        onClick={(e) => { e.stopPropagation(); abrirMaquina(item.machine_id); }}
                      >
                        {item.machine_name}
                      </button>
                    </td>
                    <td data-label={singular}>{item.customer_name || `Sem ${singularMin}`}</td>
                    <td data-label="Horário perdido">{fmtDate(item.agendado_em, { short: true })}</td>
                    <td data-label="Atraso">
                      <strong style={{ color: "var(--err)" }}>{fmtAtraso(item.minutos_de_atraso)}</strong>
                    </td>
                    <td data-label="Último backup">
                      <span className="celula-linha">
                        {fmtDate(item.last_backup_at, { short: true, empty: "nunca" })}
                        {item.last_backup_status && <StatusBadge status={item.last_backup_status} />}
                      </span>
                    </td>
                    <td data-label="Comunicação">
                      <span className="celula-linha">
                        <span className={`dot ${item.online ? "ok" : "err"}`} />
                        {item.online ? "Online" : `Offline desde ${fmtDate(item.last_seen, { short: true, empty: "sempre" })}`}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

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
              onClick={async () => {
                if (await confirmar({
                  title: "Restaurar padrão",
                  message: "Restaurar a ordem, as larguras e mostrar todas as máquinas?",
                  confirmLabel: "Restaurar",
                  variant: "warning",
                })) {
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
                  placeholder={`Buscar ${singularMin} ou máquina...`}
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
                        <strong>{m.customer_name || `Sem ${singularMin}`}</strong> — {m.name}
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
      <div className="section-title overview-barra">
        <Server size={15} /> Máquinas
        {!editing && (
          <div className="overview-vista">
            <select
              className="form-input"
              value={vista.ordem}
              onChange={(e) => vista.mudar({ ordem: e.target.value === "personalizada" ? "personalizada" : "gravidade" })}
              aria-label="Ordem das máquinas"
            >
              <option value="gravidade">Problemas primeiro</option>
              <option value="personalizada">Minha ordem</option>
            </select>
            <div className="segmentado" role="group" aria-label="Visualização">
              <button
                type="button"
                className={vista.modo === "cards" ? "ativo" : ""}
                aria-pressed={vista.modo === "cards"}
                onClick={() => vista.mudar({ modo: "cards" })}
              >
                <LayoutGrid size={14} /> Cards
              </button>
              <button
                type="button"
                className={vista.modo === "lista" ? "ativo" : ""}
                aria-pressed={vista.modo === "lista"}
                onClick={() => vista.mudar({ modo: "lista" })}
              >
                <List size={14} /> Lista
              </button>
            </div>
          </div>
        )}
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
      ) : modoLista ? (
        <div className="table-wrap">
          <table className="tabela-cartoes">
            <thead>
              <tr>
                <th>Máquina</th>
                <th>Situação</th>
                <th>{singular}</th>
                <th>Comunicação</th>
                <th>Último backup</th>
              </tr>
            </thead>
            <tbody>
              {ordenadas.map(m => {
                const g = gravidadeDa(m, semBackup);
                const sb = semBackup.get(m.id);
                return (
                  <tr key={m.id} className="linha-clicavel" onClick={() => abrirMaquina(m.id)}>
                    <td data-label="">
                      <button
                        type="button"
                        className="link-botao"
                        onClick={(e) => { e.stopPropagation(); abrirMaquina(m.id); }}
                      >
                        {m.name}
                      </button>
                    </td>
                    <td data-label="Situação">
                      <span
                        className={`badge ${g.tom}`}
                        title={sb ? `Sem o backup de ${fmtDate(sb.agendado_em, { short: true })}` : undefined}
                      >
                        <span className={`dot ${g.tom}`} />
                        {sb && g.nivel === 1 ? `Sem backup há ${fmtAtraso(sb.minutos_de_atraso)}` : g.rotulo}
                      </span>
                    </td>
                    <td data-label={singular}>{m.customer_name || `Sem ${singularMin}`}</td>
                    <td data-label="Comunicação">
                      {m.active && m.is_online
                        ? "Online"
                        : m.active
                          ? `Offline desde ${fmtDate(m.last_seen, { short: true, empty: "sempre" })}`
                          : "Desativada"}
                    </td>
                    <td data-label="Último backup">
                      <span className="celula-linha">
                        {fmtDate(m.last_backup_at, { short: true, empty: "nunca" })}
                        {m.last_backup_status && <StatusBadge status={m.last_backup_status} />}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="overview-grid">
          {ordenadas.map((m) => {
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
                  semBackup={semBackup.get(m.id)}
                />
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
