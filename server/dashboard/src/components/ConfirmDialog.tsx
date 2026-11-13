import { createContext, useContext, useState, useCallback, useEffect, useRef, ReactNode } from "react";
import { AlertTriangle, Info, HelpCircle } from "lucide-react";

/**
 * Confirmação no padrão do sistema (substitui o `confirm()` do navegador).
 *
 * Uso:
 *   const confirmar = useConfirm();
 *   if (!(await confirmar({ title: "Excluir cliente", message: "...", variant: "danger", confirmLabel: "Excluir" }))) return;
 *
 * Também aceita só o texto: `await confirmar("Gerar nova chave?")`.
 */
export type ConfirmVariant = "danger" | "warning" | "info";

export interface ConfirmOptions {
  title?: string;
  message: ReactNode;
  /** Texto do botão de confirmar. Padrão: "Confirmar". */
  confirmLabel?: string;
  /** Texto do botão de cancelar. Padrão: "Cancelar". */
  cancelLabel?: string;
  /** danger = ação destrutiva (vermelho); warning = atenção (âmbar); info = neutra (roxo). */
  variant?: ConfirmVariant;
}

type ConfirmFn = (opts: ConfirmOptions | string) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn>(() => Promise.resolve(false));

interface Pending extends ConfirmOptions { resolve: (v: boolean) => void; }

const ICONS = { danger: AlertTriangle, warning: AlertTriangle, info: HelpCircle };
const DEFAULT_TITLE = { danger: "Confirmar exclusão", warning: "Atenção", info: "Confirmar ação" };

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<Pending | null>(null);
  const confirmBtn = useRef<HTMLButtonElement>(null);

  const confirmar = useCallback<ConfirmFn>((opts) => {
    const o: ConfirmOptions = typeof opts === "string" ? { message: opts } : opts;
    return new Promise<boolean>((resolve) => setPending({ ...o, resolve }));
  }, []);

  const fechar = useCallback((resposta: boolean) => {
    setPending((p) => { p?.resolve(resposta); return null; });
  }, []);

  useEffect(() => {
    if (!pending) return;
    confirmBtn.current?.focus();
    const fn = (e: KeyboardEvent) => { if (e.key === "Escape") fechar(false); };
    document.addEventListener("keydown", fn);
    return () => document.removeEventListener("keydown", fn);
  }, [pending, fechar]);

  const variant = pending?.variant ?? "info";
  const Icon = pending ? (variant === "info" ? Info : ICONS[variant]) : Info;

  return (
    <ConfirmContext.Provider value={confirmar}>
      {children}
      {pending && (
        <div className="modal-overlay confirm-overlay" onClick={(e) => e.target === e.currentTarget && fechar(false)}>
          <div className={`modal confirm-dialog ${variant}`} role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
            <div className="confirm-icon"><Icon size={22} /></div>
            <div className="confirm-body">
              <h2 id="confirm-title" className="confirm-title">{pending.title ?? DEFAULT_TITLE[variant]}</h2>
              <div className="confirm-message">{pending.message}</div>
            </div>
            <div className="confirm-actions">
              <button className="btn btn-secondary" onClick={() => fechar(false)}>
                {pending.cancelLabel ?? "Cancelar"}
              </button>
              <button
                ref={confirmBtn}
                className={`btn ${variant === "danger" ? "btn-danger-solid" : "btn-primary"}`}
                onClick={() => fechar(true)}
              >
                {pending.confirmLabel ?? "Confirmar"}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}

export const useConfirm = () => useContext(ConfirmContext);
