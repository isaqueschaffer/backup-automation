import type { ReactNode } from "react";
import Sidebar from "./Sidebar";
import AvisoConta from "./AvisoConta";
import NotificacoesPopup from "./NotificacoesPopup";

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="app-layout">
      <Sidebar />
      <main className="main-content">
        <AvisoConta />
        <NotificacoesPopup />
        {children}
      </main>
    </div>
  );
}
