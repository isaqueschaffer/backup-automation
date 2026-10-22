interface Props { status: string | null | undefined; }

const map: Record<string, { cls: string; dot: string; label: string }> = {
  OK:      { cls: "ok",   dot: "ok",   label: "OK" },
  ONLINE:  { cls: "ok",   dot: "ok",   label: "Online" },
  OFFLINE: { cls: "err",  dot: "err",  label: "Offline" },
  PARTIAL: { cls: "warn", dot: "warn", label: "Parcial" },
  PARCIAL: { cls: "warn", dot: "warn", label: "Parcial" },
  ERROR:   { cls: "err",  dot: "err",  label: "Erro" },
  ERRO:    { cls: "err",  dot: "err",  label: "Erro" },
  ERRO_COMUNICACAO: { cls: "err", dot: "err", label: "Erro Comunicação" },
  COM_GRAVACAO: { cls: "ok", dot: "ok", label: "Gravando" },
  SEM_GRAVACAO: { cls: "warn", dot: "warn", label: "Sem Gravação" },
  NAO_VERIFICADO: { cls: "muted", dot: "muted", label: "Não Verificado" },
  EM_ANDAMENTO: { cls: "warn", dot: "warn", label: "Em andamento" },
  NAO_EXECUTOU: { cls: "err", dot: "", label: "Não executou" },
  SEM_ARQUIVOS:{ cls: "ok", dot: "ok", label: "Apenas Gravações (Sem Backup de Config)" },
  NAO_INICIALIZADO: { cls: "warn", dot: "warn", label: "Não Inicializado" },
  NAO_FORMATADO: { cls: "warn", dot: "warn", label: "Não Formatado" },
  REPOUSO: { cls: "muted", dot: "muted", label: "Repouso" },
  DESCONHECIDO: { cls: "muted", dot: "muted", label: "Desconhecido" },
  UP: { cls: "ok", dot: "ok", label: "Conectado" },
  DOWN: { cls: "err", dot: "err", label: "Desconectado" },
};

export default function StatusBadge({ status }: Props) {
  const cfg = map[status || ""] || { cls: "muted", dot: "", label: status || "—" };
  return (
    <span className={`badge ${cfg.cls}`}>
      {cfg.dot && <span className={`dot ${cfg.dot}`} />}
      {cfg.label}
    </span>
  );
}
