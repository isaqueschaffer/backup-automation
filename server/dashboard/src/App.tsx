import { lazy, Suspense, type ReactNode } from "react";
import { Routes, Route, Navigate, useParams } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { ToastProvider } from "./components/Toast";
import { ConfirmProvider } from "./components/ConfirmDialog";
import Layout from "./components/Layout";
import NovaVersao from "./components/NovaVersao";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
// Telas carregadas sob demanda (React.lazy): o painel abre baixando só o login e a Visão Geral; antes era um
// arquivo único de 1,1 MB.
const CustomersPage = lazy(() => import("./pages/Customers/CustomersPage"));
const CustomerDetail = lazy(() => import("./pages/Customers/CustomerDetail"));
const MachinesPage = lazy(() => import("./pages/Machines/MachinesPage"));
const MachineDetail = lazy(() => import("./pages/Machines/MachineDetail"));
const Backups = lazy(() => import("./pages/Backups"));
const Settings = lazy(() => import("./pages/Settings"));
const VersoesAgente = lazy(() => import("./pages/VersoesAgente"));
const PublicDashboardPage = lazy(() => import("./pages/Dashboards/PublicDashboardPage"));
const DashboardAdminPage = lazy(() => import("./pages/Dashboards/DashboardAdminPage"));
const ContasPage = lazy(() => import("./pages/Contas/ContasPage"));
const ContaDetalhePage = lazy(() => import("./pages/Contas/ContaDetalhePage"));
const MinhaConta = lazy(() => import("./pages/MinhaConta"));
const NotificacoesPage = lazy(() => import("./pages/Notificacoes/NotificacoesPage"));
const AuditoriaPage = lazy(() => import("./pages/Auditoria/AuditoriaPage"));

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, me } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (me === null) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: 80 }}>
        <span className="spinner" />
      </div>
    );
  }

  return <>{children}</>;
}

function SuperAdminRoute({ children }: { children: ReactNode }) {
  const { me } = useAuth();

  if (me && me.usuario.papel !== "SUPER_ADMIN") {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

// Auditoria: só ADMIN e super admin (visualizador e somente leitura voltam para a visão geral)
function SemLeituraRoute({ children }: { children: ReactNode }) {
  const { me } = useAuth();

  if (me && (me.usuario.papel === "LEITURA" || me.usuario.papel === "VISUALIZADOR")) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

// Rotas antigas do painel: [caminho antigo sem barra, destino]
// (antes "Clientes" ficava em units e a lista de máquinas em clients)
const LEGACY_REDIRECTS: [string, string][] = [
  ["units", "/clientes"],
  ["clients", "/maquinas"],
];

// Links antigos /clients/:id apontavam para a máquina
function LegacyMachineRedirect() {
  const { id } = useParams<{ id: string }>();
  return <Navigate to={id ? `/maquinas/${id}` : "/maquinas"} replace />;
}

function AppRoutes() {
  const { isAuthenticated } = useAuth();
  return (
    <Suspense fallback={<div className="loading-state"><div className="spinner" /></div>}>
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/" element={<ProtectedRoute><Layout><Overview /></Layout></ProtectedRoute>} />
      <Route path="/clientes" element={<ProtectedRoute><Layout><CustomersPage /></Layout></ProtectedRoute>} />
      <Route path="/clientes/:id" element={<ProtectedRoute><Layout><CustomerDetail /></Layout></ProtectedRoute>} />
      <Route path="/clientes/:id/dashboard" element={<ProtectedRoute><Layout><DashboardAdminPage /></Layout></ProtectedRoute>} />
      <Route path="/maquinas" element={<ProtectedRoute><Layout><MachinesPage /></Layout></ProtectedRoute>} />
      <Route path="/maquinas/:id" element={<ProtectedRoute><Layout><MachineDetail /></Layout></ProtectedRoute>} />
      <Route path="/backups" element={<ProtectedRoute><Layout><Backups /></Layout></ProtectedRoute>} />
      <Route path="/minha-conta" element={<ProtectedRoute><Layout><MinhaConta /></Layout></ProtectedRoute>} />
      <Route path="/notificacoes" element={<ProtectedRoute><Layout><NotificacoesPage /></Layout></ProtectedRoute>} />
      <Route path="/auditoria" element={<ProtectedRoute><SemLeituraRoute><Layout><AuditoriaPage /></Layout></SemLeituraRoute></ProtectedRoute>} />
      <Route
        path="/contas"
        element={
          <ProtectedRoute>
            <SuperAdminRoute>
              <Layout>
                <ContasPage />
              </Layout>
            </SuperAdminRoute>
          </ProtectedRoute>
        }
      />
      <Route
        path="/contas/:id"
        element={
          <ProtectedRoute>
            <SuperAdminRoute>
              <Layout>
                <ContaDetalhePage />
              </Layout>
            </SuperAdminRoute>
          </ProtectedRoute>
        }
      />
      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <SuperAdminRoute>
              <Layout>
                <Settings />
              </Layout>
            </SuperAdminRoute>
          </ProtectedRoute>
        }
      />
      <Route
        path="/versoes-agente"
        element={
          <ProtectedRoute>
            <SuperAdminRoute>
              <Layout>
                <VersoesAgente />
              </Layout>
            </SuperAdminRoute>
          </ProtectedRoute>
        }
      />
      {/* Redirecionamentos das rotas antigas */}
      {LEGACY_REDIRECTS.map(([from, to]) => (
        <Route key={from} path={`/${from}`} element={<Navigate to={to} replace />} />
      ))}
      <Route path="/clients/:id" element={<LegacyMachineRedirect />} />
      <Route path="/d" element={<PublicDashboardPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </Suspense>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <ConfirmProvider>
          <AppRoutes />
          <NovaVersao />
        </ConfirmProvider>
      </ToastProvider>
    </AuthProvider>
  );
}
