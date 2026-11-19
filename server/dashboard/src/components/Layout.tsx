import { useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { Menu, Server } from "lucide-react";
import Sidebar from "./Sidebar";
import AvisoConta from "./AvisoConta";
import NotificacoesPopup from "./NotificacoesPopup";

export default function Layout({ children }: { children: ReactNode }) {
  // No celular a barra lateral vira gaveta; no desktop o estado é ignorado (CSS).
  const [menuAberto, setMenuAberto] = useState(false);
  const { pathname } = useLocation();

  useEffect(() => {
    setMenuAberto(false);
  }, [pathname]);

  useEffect(() => {
    if (!menuAberto) return;
    const fn = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuAberto(false);
    };
    document.addEventListener("keydown", fn);
    return () => document.removeEventListener("keydown", fn);
  }, [menuAberto]);

  return (
    <div className="app-layout">
      <header className="mobile-topbar">
        <button
          type="button"
          className="mobile-menu-btn"
          aria-label={menuAberto ? "Fechar menu" : "Abrir menu"}
          aria-expanded={menuAberto}
          aria-controls="menu-lateral"
          onClick={() => setMenuAberto((v) => !v)}
        >
          <Menu size={22} />
        </button>
        <span className="mobile-topbar-title">
          <Server size={16} /> TRILAN BACKUPS
        </span>
      </header>
      <div
        className={`sidebar-backdrop${menuAberto ? " visivel" : ""}`}
        onClick={() => setMenuAberto(false)}
        aria-hidden="true"
      />
      <Sidebar aberta={menuAberto} onFechar={() => setMenuAberto(false)} />
      <main className="main-content">
        <AvisoConta />
        <NotificacoesPopup />
        {children}
      </main>
    </div>
  );
}
