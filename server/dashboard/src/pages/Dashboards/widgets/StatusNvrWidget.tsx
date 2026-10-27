import type { ContagemStatusCameras, DadosStatusNvr, WidgetInstancia } from "../types";
import useElementSize from "../useElementSize";
import PieChart, { type FatiaPizza } from "../PieChart";

export const CORES_STATUS_CAMERA = {
  gravando: "var(--ok)",
  sem_gravacao: "var(--warn)",
  offline: "var(--err)",
  nao_verificado: "var(--text-muted)",
} as const;

function montarFatias(contagem: ContagemStatusCameras): FatiaPizza[] {
  return [
    { rotulo: "Gravando", valor: contagem.gravando, cor: CORES_STATUS_CAMERA.gravando },
    { rotulo: "Sem gravação", valor: contagem.sem_gravacao, cor: CORES_STATUS_CAMERA.sem_gravacao },
    { rotulo: "Offline", valor: contagem.offline, cor: CORES_STATUS_CAMERA.offline },
    { rotulo: "Não verificado", valor: contagem.nao_verificado, cor: CORES_STATUS_CAMERA.nao_verificado },
  ];
}

interface ItemNvr extends ContagemStatusCameras {
  id: string;
  nome: string;
  tipo: string;
  maquina: string;
}

function CartaoNvr({ eq }: { eq: ItemNvr }) {
  const [cardRef, cardSize] = useElementSize<HTMLDivElement>();
  const cardWidth = cardSize.width;

  // Tamanho da pizza entre 70 e 150px calculado a partir da largura do cartão
  const tamanhoPizza =
    cardWidth > 0
      ? Math.max(70, Math.min(150, Math.round(cardWidth * 0.55)))
      : 90;

  const fatias = montarFatias(eq);
  const itensLegenda = [
    { rotulo: "Gravando", valor: eq.gravando, cor: CORES_STATUS_CAMERA.gravando },
    { rotulo: "Sem gravação", valor: eq.sem_gravacao, cor: CORES_STATUS_CAMERA.sem_gravacao },
    { rotulo: "Offline", valor: eq.offline, cor: CORES_STATUS_CAMERA.offline },
    { rotulo: "Não verificado", valor: eq.nao_verificado, cor: CORES_STATUS_CAMERA.nao_verificado },
  ];

  return (
    <div
      ref={cardRef}
      style={{
        backgroundColor: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: 10,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        minWidth: 0,
      }}
    >
      {/* Nome do NVR e máquina */}
      <div style={{ minWidth: 0 }}>
        <div
          title={eq.nome}
          style={{
            fontWeight: 600,
            fontSize: 13,
            color: "var(--text-primary)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {eq.nome}
        </div>
        <div
          title={eq.maquina}
          style={{
            fontSize: 11,
            color: "var(--text-muted)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {eq.maquina}
        </div>
      </div>

      {/* Pizza com total no centro */}
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          margin: "auto 0",
        }}
      >
        <PieChart fatias={fatias} tamanho={tamanhoPizza} rotuloCentro={String(eq.total)} />
      </div>

      {/* Legenda compacta abaixo */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "4px 8px",
          fontSize: 11,
          borderTop: "1px solid var(--border)",
          paddingTop: 8,
        }}
      >
        {itensLegenda.map((item) => (
          <div
            key={item.rotulo}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              minWidth: 0,
            }}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: 2,
                backgroundColor: item.cor,
                flexShrink: 0,
              }}
            />
            <span
              title={item.rotulo}
              style={{
                color: "var(--text-secondary)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                flex: 1,
              }}
            >
              {item.rotulo}
            </span>
            <span
              style={{
                fontWeight: 600,
                color: "var(--text-primary)",
                flexShrink: 0,
              }}
            >
              {item.valor}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function StatusNvrWidget({
  dados,
}: {
  dados: DadosStatusNvr;
  widget: WidgetInstancia;
}) {
  const [containerRef, containerSize] = useElementSize<HTMLDivElement>();

  if (!dados.equipamentos || dados.equipamentos.length === 0) {
    return (
      <div
        style={{
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text-muted)",
          fontSize: 12,
        }}
      >
        Nenhum NVR com câmeras neste cliente.
      </div>
    );
  }

  // Visual agregado: uma única pizza centralizada com legenda completa
  if (dados.visual === "agregado") {
    const { width, height } = containerSize;
    const estreito = width > 0 && width < 360;

    const larguraDisponivel =
      width > 0 ? (estreito ? width - 24 : Math.max(70, width - 200)) : 140;
    const alturaDisponivel =
      height > 0 ? (estreito ? Math.max(70, height - 130) : height - 24) : 140;

    const tamanhoPizza =
      width > 0 && height > 0
        ? Math.max(70, Math.min(larguraDisponivel, alturaDisponivel))
        : 120;

    const fatiasAgregado = montarFatias(dados.total);
    const totalGeral = dados.total.total || 0;
    const itensLegenda = [
      {
        rotulo: "Gravando",
        valor: dados.total.gravando,
        cor: CORES_STATUS_CAMERA.gravando,
        pct: totalGeral > 0 ? Math.round((dados.total.gravando / totalGeral) * 100) : 0,
      },
      {
        rotulo: "Sem gravação",
        valor: dados.total.sem_gravacao,
        cor: CORES_STATUS_CAMERA.sem_gravacao,
        pct: totalGeral > 0 ? Math.round((dados.total.sem_gravacao / totalGeral) * 100) : 0,
      },
      {
        rotulo: "Offline",
        valor: dados.total.offline,
        cor: CORES_STATUS_CAMERA.offline,
        pct: totalGeral > 0 ? Math.round((dados.total.offline / totalGeral) * 100) : 0,
      },
      {
        rotulo: "Não verificado",
        valor: dados.total.nao_verificado,
        cor: CORES_STATUS_CAMERA.nao_verificado,
        pct: totalGeral > 0 ? Math.round((dados.total.nao_verificado / totalGeral) * 100) : 0,
      },
    ];

    return (
      <div
        ref={containerRef}
        style={{
          height: "100%",
          width: "100%",
          padding: 12,
          display: "flex",
          flexDirection: estreito ? "column" : "row",
          alignItems: "center",
          justifyContent: "center",
          gap: estreito ? 16 : 24,
        }}
      >
        <PieChart
          fatias={fatiasAgregado}
          tamanho={tamanhoPizza}
          rotuloCentro={String(dados.total.total)}
        />

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 8,
            minWidth: 160,
            flexShrink: 0,
          }}
        >
          {itensLegenda.map((item) => (
            <div
              key={item.rotulo}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
                fontSize: 12,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                <span
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: 2,
                    backgroundColor: item.cor,
                    flexShrink: 0,
                  }}
                />
                <span style={{ color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                  {item.rotulo}
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 4, flexShrink: 0 }}>
                <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                  {item.valor}
                </span>
                <span style={{ color: "var(--text-muted)", fontSize: 11 }}>
                  ({item.pct}%)
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Visual padrão por equipamento: grade de cartões
  return (
    <div
      ref={containerRef}
      style={{
        height: "100%",
        width: "100%",
        padding: 2,
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: 12,
        }}
      >
        {dados.equipamentos.map((eq) => (
          <CartaoNvr key={eq.id} eq={eq} />
        ))}
      </div>
    </div>
  );
}
