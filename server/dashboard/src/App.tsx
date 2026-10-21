import { Routes, Route, Navigate, useParams } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { ToastProvider } from "./components/Toast";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import CustomersPage from "./pages/Customers/CustomersPage";
import CustomerDetail from "./pages/Customers/CustomerDetail";
import MachinesPage from "./pages/Machines/MachinesPage";
import MachineDetail from "./pages/Machines/MachineDetail";
import Backups from "./pages/Backups";
import Settings from "./pages/Settings";
import PublicDashboardPage from "./pages/Dashboards/PublicDashboardPage";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
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
    <Routes>
      <Route path="/login" element={isAuthenticated ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/" element={<ProtectedRoute><Layout><Overview /></Layout></ProtectedRoute>} />
      <Route path="/clientes" element={<ProtectedRoute><Layout><CustomersPage /></Layout></ProtectedRoute>} />
      <Route path="/clientes/:id" element={<ProtectedRoute><Layout><CustomerDetail /></Layout></ProtectedRoute>} />
      <Route path="/maquinas" element={<ProtectedRoute><Layout><MachinesPage /></Layout></ProtectedRoute>} />
      <Route path="/maquinas/:id" element={<ProtectedRoute><Layout><MachineDetail /></Layout></ProtectedRoute>} />
      <Route path="/backups" element={<ProtectedRoute><Layout><Backups /></Layout></ProtectedRoute>} />
      <Route path="/settings" element={<ProtectedRoute><Layout><Settings /></Layout></ProtectedRoute>} />
      {/* Redirecionamentos das rotas antigas */}
      {LEGACY_REDIRECTS.map(([from, to]) => (
        <Route key={from} path={`/${from}`} element={<Navigate to={to} replace />} />
      ))}
      <Route path="/clients/:id" element={<LegacyMachineRedirect />} />
      <Route path="/d" element={<PublicDashboardPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <AppRoutes />
      </ToastProvider>
    </AuthProvider>
  );
}
