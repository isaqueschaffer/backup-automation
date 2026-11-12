import { useEffect, useState } from "react";
import { AlertCircle, Link2Off, RefreshCw, WifiOff } from "lucide-react";
import {
  fetchPublicDashboard,
  fetchPublicData,
  fetchPublicOptions,
  fetchPublicPreview,
  savePublicLayout,
} from "../../api/dashboards";
import { DadosDashboard, DashboardPublico } from "./types";
import DashboardWorkspace from "./DashboardWorkspace";

type TipoErro = "invalido" | "limite" | "rede";

function classificarErro(err: unknown): TipoErro {
  if (err && typeof err === "object" && "response" in err) {
    const res = (err as { response?: { status?: number } }).response;
    if (res?.status === 404 || res?.status === 403 || res?.status === 401) {
      return "invalido";
    }
    if (res?.status === 429) {
      return "limite";
    }
  }
  return "rede";
}

function fmtHora(isoStr: string | null | undefined): string {
  if (!isoStr) return "";
  const str = isoStr.endsWith("Z") ? isoStr : `${isoStr}Z`;
  const d = new Date(str);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function PublicDashboardPage() {
  const [token] = useState<string>(() => {
    if (typeof window === "undefined") return "";
    return window.location.hash.replace(/^#/, "").trim();
  });

  const [carregando, setCarregando] = useState<boolean>(Boolean(token));
  const [atualizando, setAtualizando] = useState<boolean>(false);
  const [erro, setErro] = useState<TipoErro | null>(token ? null : "invalido");
  const [dashboard, setDashboard] = useState<DashboardPublico | null>(null);
  const [dados, setDados] = useState<DadosDashboard | null>(null);
  const [semConexao, setSemConexao] = useState<boolean>(false);

  // Efeito de privacidade e metatags no head
  useEffect(() => {
    const originalTitle = document.title;
    document.title = "Dashboard";

    const robotsMeta = document.createElement("meta");
    robotsMeta.name = "robots";
    robotsMeta.content = "noindex,nofollow";
    document.head.appendChild(robotsMeta);

    const referrerMeta = document.createElement("meta");
    referrerMeta.name = "referrer";
    referrerMeta.content = "no-referrer";
    document.head.appendChild(referrerMeta);

    return () => {
      document.title = originalTitle;
      if (robotsMeta.parentNode) {
        robotsMeta.parentNode.removeChild(robotsMeta);
      }
      if (referrerMeta.parentNode) {
        referrerMeta.parentNode.removeChild(referrerMeta);
      }
    };
  }, []);

  // Carga inicial e atualização periódica a cada 30 segundos
  useEffect(() => {
    if (!token) return;
    let cancelado = false;

    fetchPublicDashboard(token)
      .then((dash) => {
        if (cancelado) return;
        setDashboard(dash);
        setDados(dash.dados);
        setCarregando(false);
        setErro(null);
        setSemConexao(false);
      })
      .catch((err) => {
        if (cancelado) return;
        setCarregando(false);
        setErro(classificarErro(err));
      });

    const intervalo = setInterval(() => {
      fetchPublicData(token)
        .then((novosDados) => {
          if (cancelado) return;
          setDados(novosDados);
          setSemConexao(false);
        })
        .catch((err) => {
          if (cancelado) return;
          const tipo = classificarErro(err);
          if (tipo === "invalido") {
            setErro("invalido");
          } else {
            setSemConexao(true);
          }
        });
    }, 30000);

    return () => {
      cancelado = true;
      clearInterval(intervalo);
    };
  }, [token]);

  const recarregar = () => {
    if (!token || atualizando) return;
    setAtualizando(true);
    fetchPublicData(token)
      .then((novosDados) => {
        setDados(novosDados);
        setSemConexao(false);
      })
      .catch((err) => {
        const tipo = classificarErro(err);
        if (tipo === "invalido") {
          setErro("invalido");
        } else {
          setSemConexao(true);
        }
      })
      .finally(() => {
        setAtualizando(false);
      });
  };

  const recarregarCompleto = () => {
    if (!token) return;
    fetchPublicDashboard(token)
      .then((dash) => {
        setDashboard(dash);
        setDados(dash.dados);
        setSemConexao(false);
      })
      .catch((err) => {
        const tipo = classificarErro(err);
        if (tipo === "invalido") {
          setErro("invalido");
        } else {
          setSemConexao(true);
        }
      });
  };

  if (erro) {
    let titulo = "Não foi possível carregar o dashboard";
    let detalhe = "Verifique sua conexão com a internet e tente novamente.";
    let Icone = AlertCircle;
    let iconeCor = "var(--err)";

    if (erro === "invalido") {
      titulo = "Link inválido ou expirado";
      detalhe = "Peça um novo link à equipe responsável.";
      Icone = Link2Off;
      iconeCor = "var(--err)";
    } else if (erro === "limite") {
      titulo = "Muitas tentativas. Aguarde alguns minutos.";
      detalhe = "O limite de acessos foi atingido. Tente novamente em instantes.";
      Icone = AlertCircle;
      iconeCor = "var(--warn)";
    }

    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: "var(--bg-base, var(--surface-2))",
          padding: 24,
        }}
      >
        <div
          className="card"
          style={{
            maxWidth: 420,
            width: "100%",
            padding: 32,
            textAlign: "center",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 12,
          }}
        >
          <Icone size={40} color={iconeCor} style={{ flexShrink: 0 }} />
          <h2
            style={{
              fontSize: 18,
              fontWeight: 700,
              color: "var(--text-primary)",
              margin: 0,
            }}
          >
            {titulo}
          </h2>
          <p
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              margin: 0,
              lineHeight: 1.5,
            }}
          >
            {detalhe}
          </p>
        </div>
      </div>
    );
  }

  if (carregando || !dashboard) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: "var(--bg-base, var(--surface-2))",
        }}
      >
        <span className="spinner" />
      </div>
    );
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundColor: "var(--bg-base, var(--surface-2))",
        padding: "20px 24px",
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          maxWidth: 1600,
          margin: "0 auto",
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        {/* Cabeçalho do dashboard */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 12,
          }}
        >
          <div>
            <h1
              style={{
                fontSize: 22,
                fontWeight: 700,
                color: "var(--text-primary)",
                margin: 0,
              }}
            >
              {dashboard.cliente_nome}
            </h1>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginTop: 4,
                fontSize: 12,
                color: "var(--text-muted)",
              }}
            >
              {dados?.gerado_em && (
                <span>Atualizado às {fmtHora(dados.gerado_em)}</span>
              )}
              {semConexao && (
                <span
                  style={{
                    color: "var(--warn)",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                    fontSize: 11,
                  }}
                >
                  <WifiOff size={12} style={{ flexShrink: 0 }} />
                  Sem conexão — tentando novamente
                </span>
              )}
            </div>
          </div>

          <button
            type="button"
            className="btn btn-secondary"
            onClick={recarregar}
            disabled={atualizando}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 13,
            }}
          >
            <RefreshCw
              size={14}
              style={{
                flexShrink: 0,
                transform: atualizando ? "rotate(180deg)" : "none",
                transition: "transform 0.4s ease",
              }}
            />
            Atualizar
          </button>
        </div>

        {/* Grade de widgets */}
        <DashboardWorkspace
          layout={dashboard.layout}
          version={dashboard.version}
          dadosVivos={dados}
          podeEditar={dashboard.pode_editar}
          carregarOpcoes={() => fetchPublicOptions(token)}
          previa={(l) => fetchPublicPreview(token, l)}
          salvar={(l, v) => savePublicLayout(token, l, v)}
          onSalvo={(r) =>
            setDashboard((d) =>
              d ? { ...d, layout: r.layout, version: r.version } : d
            )
          }
          onConflito={recarregarCompleto}
        />
      </div>
    </div>
  );
}
