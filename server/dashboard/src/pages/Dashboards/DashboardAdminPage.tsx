import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import {
  fetchDashboard,
  fetchDashboardData,
  fetchDashboardOptions,
  fetchDashboardPreview,
  restoreDashboardDefault,
  saveDashboardLayout,
} from "../../api/dashboards";
import { useToast } from "../../components/Toast";
import { apiErrorMessage } from "../../utils/errors";
import { Compartilhamento, DadosDashboard, DashboardAdmin } from "./types";
import DashboardWorkspace from "./DashboardWorkspace";

// Página administrativa de configuração do dashboard do cliente
export default function DashboardAdminPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [dashboard, setDashboard] = useState<DashboardAdmin | null>(null);
  const [dados, setDados] = useState<DadosDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [erroCarga, setErroCarga] = useState(false);

  const carregarDados = useCallback(
    async () => {
      if (!id) return;
      try {
        const d = await fetchDashboardData(id);
        setDados(d);
      } catch {
        // Falha silenciosa no polling
      }
    },
    [id]
  );

  const carregarTudo = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setNotFound(false);
    setErroCarga(false);
    try {
      const dash = await fetchDashboard(id);
      setDashboard(dash);
      await carregarDados();
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 404) {
        setNotFound(true);
      } else {
        setErroCarga(true);
        toast(apiErrorMessage(err, "Erro ao carregar dashboard do cliente."), "error");
      }
    } finally {
      setLoading(false);
    }
  }, [id, carregarDados, toast]);

  useEffect(() => {
    carregarTudo();
  }, [carregarTudo]);

  useEffect(() => {
    if (!id || notFound || erroCarga) return;
    const interval = setInterval(() => {
      carregarDados();
    }, 30000);
    return () => clearInterval(interval);
  }, [id, notFound, erroCarga, carregarDados]);

  const renderBadge = (comp?: Compartilhamento) => {
    if (!comp || !comp.tem_link) {
      return <span className="badge muted">Sem link</span>;
    }
    if (comp.expirado) {
      return <span className="badge err">Link expirado</span>;
    }
    if (!comp.ativo) {
      return <span className="badge warn">Link desativado</span>;
    }
    return <span className="badge ok">Link ativo</span>;
  };

  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          minHeight: 300,
        }}
      >
        <span className="spinner" />
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="card" style={{ padding: 40, textAlign: "center" }}>
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
          Cliente não encontrado
        </div>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => navigate("/clientes")}
        >
          Voltar para Clientes
        </button>
      </div>
    );
  }

  if (erroCarga || !dashboard || !id) {
    return (
      <div className="card" style={{ padding: 40, textAlign: "center" }}>
        <div
          style={{
            fontSize: 16,
            fontWeight: 600,
            marginBottom: 12,
            color: "var(--err)",
          }}
        >
          Não foi possível carregar o dashboard
        </div>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => carregarTudo()}
        >
          Tentar novamente
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            type="button"
            className="btn-icon"
            onClick={() => navigate(`/clientes/${id}`)}
            title="Voltar ao cliente"
          >
            <ArrowLeft size={16} />
          </button>
          <div>
            <h1 className="page-title">Dashboard — {dashboard.cliente_nome}</h1>
            <p className="page-subtitle">
              Monte o painel deste cliente. O link de compartilhamento mostra exatamente este layout.
            </p>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {renderBadge(dashboard.compartilhamento)}
        </div>
      </div>

      <DashboardWorkspace
        layout={dashboard.layout}
        version={dashboard.version}
        dadosVivos={dados}
        podeEditar
        carregarOpcoes={() => fetchDashboardOptions(id)}
        previa={(l) => fetchDashboardPreview(id, l)}
        salvar={(l, v) => saveDashboardLayout(id, l, v)}
        restaurar={() => restoreDashboardDefault(id)}
        onSalvo={(r) =>
          setDashboard((d) => (d ? { ...d, layout: r.layout, version: r.version } : d))
        }
        onConflito={carregarTudo}
      />
    </div>
  );
}
