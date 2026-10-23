import { DadosResumo, WidgetInstancia } from "../types";

interface Props {
  dados: DadosResumo;
  widget: WidgetInstancia;
}

export default function ResumoWidget({ dados }: Props) {
  const maqsCor =
    dados.maquinas_total === 0
      ? "var(--text-secondary)"
      : dados.maquinas_online === dados.maquinas_total
      ? "var(--ok)"
      : dados.maquinas_online === 0
      ? "var(--err)"
      : "var(--warn)";

  const camsCor =
    dados.cameras_total === 0
      ? "var(--text-secondary)"
      : dados.cameras_online === dados.cameras_total
      ? "var(--ok)"
      : dados.cameras_online === 0
      ? "var(--err)"
      : "var(--warn)";

  const tiles = [
    {
      rotulo: "Máquinas online",
      valor: `${dados.maquinas_online}/${dados.maquinas_total}`,
      cor: maqsCor,
    },
    {
      rotulo: "Backups OK",
      valor: dados.backups_ok,
      cor: dados.backups_ok > 0 ? "var(--ok)" : "var(--text-secondary)",
    },
    {
      rotulo: "Backups com falha",
      valor: dados.backups_com_falha,
      cor: dados.backups_com_falha > 0 ? "var(--err)" : "var(--text-secondary)",
    },
    {
      rotulo: "Sem backup",
      valor: dados.sem_backup,
      cor: dados.sem_backup > 0 ? "var(--warn)" : "var(--text-secondary)",
    },
    {
      rotulo: "Equipamentos",
      valor: dados.equipamentos_total,
      cor: "var(--text-primary)",
    },
    {
      rotulo: "Câmeras online",
      valor: `${dados.cameras_online}/${dados.cameras_total}`,
      cor: camsCor,
    },
    {
      rotulo: "Câmeras offline",
      valor: dados.cameras_offline,
      cor: dados.cameras_offline > 0 ? "var(--err)" : "var(--text-secondary)",
    },
    {
      rotulo: "Sem gravação",
      valor: dados.cameras_sem_gravacao,
      cor: dados.cameras_sem_gravacao > 0 ? "var(--warn)" : "var(--text-secondary)",
    },
  ];

  if ((dados.discos_total || 0) > 0) {
    tiles.push(
      {
        rotulo: "Discos dos gravadores",
        valor: dados.discos_total,
        cor: "var(--text-primary)",
      },
      {
        rotulo: "Discos com problema",
        valor: dados.discos_com_problema,
        cor: dados.discos_com_problema > 0 ? "var(--err)" : "var(--ok)",
      }
    );
  }

  return (
    <div
      style={{
        height: "100%",
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
        gap: 8,
      }}
    >
      {tiles.map((t) => (
        <div
          key={t.rotulo}
          style={{
            backgroundColor: "var(--surface-2)",
            borderRadius: 6,
            padding: "8px 10px",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            border: "1px solid var(--border)",
            minHeight: 58,
          }}
        >
          <span
            style={{
              fontSize: 11,
              color: "var(--text-secondary)",
              fontWeight: 500,
              lineHeight: 1.2,
            }}
          >
            {t.rotulo}
          </span>
          <span
            style={{
              fontSize: 18,
              fontWeight: 700,
              color: t.cor,
              marginTop: 4,
            }}
          >
            {t.valor}
          </span>
        </div>
      ))}
    </div>
  );
}
