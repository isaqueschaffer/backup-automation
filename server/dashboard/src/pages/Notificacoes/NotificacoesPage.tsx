import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Bell, Pencil, Plus, Power, PowerOff, Trash2 } from "lucide-react";
import {
  apagarNotificacaoPersonalizada,
  atualizarConfigNotificacao,
  atualizarNotificacaoPersonalizada,
  criarNotificacaoPersonalizada,
  fetchConfigNotificacoes,
  fetchNotificacoes,
  fetchNotificacoesPersonalizadas,
} from "../../api/client";
import { ConfiguracaoNotificacao, Notificacao, NotificacaoPersonalizada, NotificacaoPersonalizadaPayload, TipoNotificacao } from "../../api/types";
import { useToast } from "../../components/Toast";
import { useSomenteLeitura } from "../../contexts/AuthContext";
import { fmtDate } from "../../utils/date";
import { COR_NOTIFICACAO, ICONE_NOTIFICACAO, LABEL_NOTIFICACAO } from "../../utils/notificacoes";
import NotificacaoPersonalizadaFormModal from "./NotificacaoPersonalizadaFormModal";

const DESCRICAO_TIPO: Record<TipoNotificacao, string> = {
  LICENCA_UNM2000: "Avisa quando a licença de uma OLT UNM2000 está a 10 dias ou menos do vencimento (ou já venceu). Também envia um e-mail por dia enquanto não for renovada.",
  BACKUP_FALHOU: "Avisa quando o último backup de uma máquina terminou com erro.",
  AGENTE_OFFLINE: "Avisa quando uma máquina ativa fica mais de 15 minutos sem contato com o servidor.",
  PERSONALIZADA: "",
};

const TIPOS_AUTOMATICOS: TipoNotificacao[] = ["LICENCA_UNM2000", "BACKUP_FALHOU", "AGENTE_OFFLINE"];

function resumoFrequencia(p: NotificacaoPersonalizada): string {
  if (p.modo === "RECORRENTE") return `A cada ${p.intervalo_dias} dia(s)`;
  // data_alvo é só a data (sem hora): formata direto da string "YYYY-MM-DD", sem passar por Date (evita o
  // fuso local empurrar para o dia anterior)
  const [ano, mes, dia] = (p.data_alvo || "").split("-");
  const data = ano ? `${dia}/${mes}/${ano}` : "?";
  return `${p.dias_antes} dia(s) antes de ${data}`;
}

export default function NotificacoesPage() {
  const { toast } = useToast();
  const somenteLeitura = useSomenteLeitura();

  const [abertas, setAbertas] = useState<Notificacao[]>([]);
  const [config, setConfig] = useState<ConfiguracaoNotificacao[]>([]);
  const [personalizadas, setPersonalizadas] = useState<NotificacaoPersonalizada[]>([]);
  const [loading, setLoading] = useState(true);
  const [salvando, setSalvando] = useState<TipoNotificacao | string | null>(null);
  const [formAberto, setFormAberto] = useState<"nova" | NotificacaoPersonalizada | null>(null);

  const carregar = useCallback(() => {
    setLoading(true);
    Promise.all([fetchNotificacoes(true), fetchConfigNotificacoes(), fetchNotificacoesPersonalizadas()])
      .then(([n, c, p]) => { setAbertas(n); setConfig(c); setPersonalizadas(p); })
      .catch(() => toast("Erro ao carregar notificações.", "error"))
      .finally(() => setLoading(false));
  }, [toast]);

  useEffect(() => { carregar(); }, [carregar]);

  const alternarTipo = async (tipo: TipoNotificacao, ativoAtual: boolean) => {
    setSalvando(tipo);
    try {
      await atualizarConfigNotificacao(tipo, !ativoAtual);
      toast(!ativoAtual ? "Notificação ativada." : "Notificação desativada.", "success");
      carregar();
    } catch {
      toast("Não foi possível alterar essa notificação.", "error");
    } finally {
      setSalvando(null);
    }
  };

  const alternarPersonalizada = async (p: NotificacaoPersonalizada) => {
    setSalvando(p.id);
    try {
      await atualizarNotificacaoPersonalizada(p.id, { ...p, ativo: !p.ativo });
      toast(!p.ativo ? "Notificação ativada." : "Notificação desativada.", "success");
      carregar();
    } catch {
      toast("Não foi possível alterar essa notificação.", "error");
    } finally {
      setSalvando(null);
    }
  };

  const apagarPersonalizada = async (p: NotificacaoPersonalizada) => {
    if (!confirm(`Apagar a notificação "${p.titulo}"?`)) return;
    try {
      await apagarNotificacaoPersonalizada(p.id);
      toast("Notificação apagada.", "success");
      carregar();
    } catch {
      toast("Não foi possível apagar essa notificação.", "error");
    }
  };

  const salvarPersonalizada = async (payload: NotificacaoPersonalizadaPayload) => {
    if (formAberto && formAberto !== "nova") {
      await atualizarNotificacaoPersonalizada(formAberto.id, payload);
      toast("Notificação atualizada.", "success");
    } else {
      await criarNotificacaoPersonalizada(payload);
      toast("Notificação criada.", "success");
    }
    setFormAberto(null);
    carregar();
  };

  if (loading) return <div className="loading-state"><div className="spinner" /></div>;

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Notificações</h1>
          <p className="page-subtitle">Alertas em aberto e preferências de aviso</p>
        </div>
      </div>

      <div style={{ display: "grid", gap: 20, maxWidth: 820 }}>
        <div className="card">
          <div className="section-title"><Bell size={15} />Alertas em aberto ({abertas.length})</div>
          {abertas.length === 0 ? (
            <p className="text-sm text-muted">Nenhum alerta no momento.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {abertas.map((n) => {
                const Icone = ICONE_NOTIFICACAO[n.tipo];
                const cor = COR_NOTIFICACAO[n.tipo];
                return (
                  <div
                    key={n.id}
                    style={{
                      display: "flex", gap: 10, alignItems: "flex-start", padding: "10px 12px",
                      border: "1px solid var(--border)", borderLeft: `3px solid ${cor}`, borderRadius: "var(--radius-sm)",
                    }}
                  >
                    <Icone size={18} color={cor} style={{ flexShrink: 0, marginTop: 2 }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600 }}>{n.titulo}</div>
                      <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>{n.mensagem}</div>
                    </div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                      {fmtDate(n.criado_em, { short: true })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="card">
          <div className="section-title"><Bell size={15} />Preferências de notificação</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {config.filter((c) => TIPOS_AUTOMATICOS.includes(c.tipo)).map(({ tipo, ativo }) => {
              const Icone = ICONE_NOTIFICACAO[tipo];
              const cor = COR_NOTIFICACAO[tipo];
              return (
                <div
                  key={tipo}
                  style={{
                    display: "flex", gap: 12, alignItems: "center", padding: "10px 4px",
                    borderBottom: "1px solid var(--border)",
                  }}
                >
                  <Icone size={16} color={cor} style={{ flexShrink: 0, opacity: ativo ? 1 : 0.4 }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600 }}>{LABEL_NOTIFICACAO[tipo]}</div>
                    <div style={{ fontSize: 12.5, color: "var(--text-muted)" }}>{DESCRICAO_TIPO[tipo]}</div>
                  </div>
                  {!somenteLeitura && (
                    <button
                      type="button"
                      className={`btn btn-sm ${ativo ? "btn-secondary" : "btn-primary"}`}
                      disabled={salvando === tipo}
                      onClick={() => alternarTipo(tipo, ativo)}
                      style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 6 }}
                    >
                      {ativo ? <Power size={13} /> : <PowerOff size={13} />}
                      {ativo ? "Ativada" : "Desativada"}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="card">
          <div className="section-title" style={{ justifyContent: "space-between", display: "flex" }}>
            <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <AlertTriangle size={15} color={COR_NOTIFICACAO.PERSONALIZADA} />Notificações personalizadas
            </span>
            {!somenteLeitura && (
              <button type="button" className="btn btn-primary btn-sm" onClick={() => setFormAberto("nova")}
                style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <Plus size={14} /> Nova
              </button>
            )}
          </div>

          {personalizadas.length === 0 ? (
            <p className="text-sm text-muted">Nenhuma notificação personalizada criada.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {personalizadas.map((p) => (
                <div
                  key={p.id}
                  style={{
                    display: "flex", gap: 12, alignItems: "center", padding: "10px 4px",
                    borderBottom: "1px solid var(--border)", opacity: p.ativo ? 1 : 0.55,
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600 }}>{p.titulo}</div>
                    <div style={{ fontSize: 12.5, color: "var(--text-muted)" }}>
                      {resumoFrequencia(p)} · {p.enviar_email ? "e-mail" : ""}{p.enviar_email && p.mostrar_popup ? " + " : ""}{p.mostrar_popup ? "pop-up" : ""}
                      {!p.enviar_email && !p.mostrar_popup && "só na lista"}
                    </div>
                  </div>
                  {!somenteLeitura && (
                    <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                      <button type="button" className="btn btn-secondary btn-sm" title="Editar" onClick={() => setFormAberto(p)}>
                        <Pencil size={13} />
                      </button>
                      <button
                        type="button" className="btn btn-secondary btn-sm" title={p.ativo ? "Desativar" : "Ativar"}
                        disabled={salvando === p.id} onClick={() => alternarPersonalizada(p)}
                      >
                        {p.ativo ? <Power size={13} /> : <PowerOff size={13} />}
                      </button>
                      <button type="button" className="btn btn-secondary btn-sm" title="Apagar" onClick={() => apagarPersonalizada(p)}>
                        <Trash2 size={13} />
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {formAberto && (
        <NotificacaoPersonalizadaFormModal
          inicial={formAberto === "nova" ? null : formAberto}
          onSalvar={salvarPersonalizada}
          onClose={() => setFormAberto(null)}
        />
      )}
    </>
  );
}
