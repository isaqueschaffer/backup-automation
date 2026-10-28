import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { apiErrorMessage } from "../utils/errors";
import { Lock, Mail, Server } from "lucide-react";
import pkg from "../../package.json";

export default function Login() {
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [modoPlataforma, setModoPlataforma] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!modoPlataforma && !email.trim()) {
      setError("Informe o e-mail.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await login(modoPlataforma ? null : email.trim(), pw);
      navigate("/");
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 429) {
        setError(apiErrorMessage(err, "Muitas tentativas. Tente novamente em alguns minutos."));
      } else if (modoPlataforma) {
        setError("Senha incorreta. Tente novamente.");
      } else {
        setError("E-mail ou senha incorretos.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <div className="login-logo-icon">
            <Server size={28} color="white" style={{ flexShrink: 0 }} />
          </div>
          <div className="login-logo-title">
            TRILAN BACKUPS{" "}
            <span
              style={{
                fontSize: "0.4em",
                backgroundColor: "var(--primary)",
                color: "white",
                padding: "2px 6px",
                borderRadius: "4px",
                marginLeft: "6px",
                fontWeight: "bold",
                verticalAlign: "middle",
              }}
            >
              V{pkg.version}
            </span>
          </div>
          <div className="login-logo-sub">Painel de Gerenciamento de Equipamentos</div>
        </div>

        {error && <div className="login-error">{error}</div>}

        <form onSubmit={handleSubmit}>
          {!modoPlataforma ? (
            <>
              <div className="form-group">
                <label className="form-label">E-mail</label>
                <div style={{ position: "relative" }}>
                  <input
                    key="email-input"
                    className="form-input"
                    type="email"
                    autoComplete="username"
                    placeholder="seu@email.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    style={{ paddingLeft: 40 }}
                    autoFocus
                  />
                  <Mail
                    size={15}
                    style={{
                      position: "absolute",
                      left: 12,
                      top: "50%",
                      transform: "translateY(-50%)",
                      color: "var(--text-muted)",
                      flexShrink: 0,
                    }}
                  />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Senha</label>
                <div style={{ position: "relative" }}>
                  <input
                    key="pw-user-input"
                    className="form-input"
                    type="password"
                    autoComplete="current-password"
                    placeholder="••••••••"
                    value={pw}
                    onChange={(e) => setPw(e.target.value)}
                    style={{ paddingLeft: 40 }}
                  />
                  <Lock
                    size={15}
                    style={{
                      position: "absolute",
                      left: 12,
                      top: "50%",
                      transform: "translateY(-50%)",
                      color: "var(--text-muted)",
                      flexShrink: 0,
                    }}
                  />
                </div>
              </div>
            </>
          ) : (
            <div className="form-group">
              <label className="form-label">Senha do administrador da plataforma</label>
              <div style={{ position: "relative" }}>
                <input
                  key="pw-plat-input"
                  className="form-input"
                  type="password"
                  autoComplete="current-password"
                  placeholder="••••••••"
                  value={pw}
                  onChange={(e) => setPw(e.target.value)}
                  style={{ paddingLeft: 40 }}
                  autoFocus
                />
                <Lock
                  size={15}
                  style={{
                    position: "absolute",
                    left: 12,
                    top: "50%",
                    transform: "translateY(-50%)",
                    color: "var(--text-muted)",
                    flexShrink: 0,
                  }}
                />
              </div>
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary w-full"
            style={{ justifyContent: "center", marginTop: 8 }}
            disabled={loading}
          >
            {loading ? <span className="spinner spinner-sm" /> : "Entrar"}
          </button>

          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => {
              setModoPlataforma((prev) => !prev);
              setError("");
            }}
            style={{
              marginTop: 12,
              width: "100%",
              justifyContent: "center",
            }}
          >
            {modoPlataforma
              ? "Entrar com e-mail"
              : "Entrar como administrador da plataforma"}
          </button>
        </form>
      </div>
    </div>
  );
}
