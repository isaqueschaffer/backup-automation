import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import { login as apiLogin, CONTA_KEY } from "../api/client";
import { fetchMe } from "../api/contas";
import type { Me } from "../api/types";

export interface AuthCtx {
  isAuthenticated: boolean;
  me: Me | null; // null enquanto carrega ou sem login
  login: (email: string | null, password: string) => Promise<void>;
  logout: () => void;
  recarregarMe: () => Promise<void>;
  contaSelecionadaId: string | null; // só super admin
  escolherConta: (contaId: string | null) => void;
}

const AuthContext = createContext<AuthCtx>({} as AuthCtx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => {
    try {
      return !!localStorage.getItem("trilan_token");
    } catch {
      return false;
    }
  });

  const [me, setMe] = useState<Me | null>(null);

  const [contaSelecionadaId, setContaSelecionadaId] = useState<string | null>(() => {
    try {
      return localStorage.getItem(CONTA_KEY);
    } catch {
      return null;
    }
  });

  const recarregarMe = useCallback(async () => {
    try {
      const data = await fetchMe();
      setMe(data);
    } catch {
      // O interceptor de 401 já leva ao login; se falhar por outro motivo, mantém estado atual
    }
  }, []);

  const login = useCallback(
    async (email: string | null, password: string) => {
      const data = await apiLogin(email, password);
      try {
        localStorage.setItem("trilan_token", data.access_token);
      } catch {
        // localStorage indisponível
      }
      setIsAuthenticated(true);
      await recarregarMe();
    },
    [recarregarMe]
  );

  const logout = useCallback(() => {
    try {
      localStorage.removeItem("trilan_token");
      localStorage.removeItem(CONTA_KEY);
    } catch {
      // localStorage indisponível
    }
    setMe(null);
    setContaSelecionadaId(null);
    setIsAuthenticated(false);
  }, []);

  const escolherConta = useCallback((contaId: string | null) => {
    try {
      if (contaId) {
        localStorage.setItem(CONTA_KEY, contaId);
      } else {
        localStorage.removeItem(CONTA_KEY);
      }
    } catch {
      // localStorage indisponível
    }
    setContaSelecionadaId(contaId);
    window.location.assign("/");
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      setMe(null);
      return;
    }

    void recarregarMe();

    const handleFocus = () => {
      void recarregarMe();
    };

    // A cada 10 min e no evento focus da janela, recarrega os dados do me
    const intervalId = window.setInterval(() => {
      void recarregarMe();
    }, 10 * 60 * 1000);

    window.addEventListener("focus", handleFocus);

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("focus", handleFocus);
    };
  }, [isAuthenticated, recarregarMe]);

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        me,
        login,
        logout,
        recarregarMe,
        contaSelecionadaId,
        escolherConta,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);

// Rótulo do agrupamento: "Cliente/Clientes" (integrador) ou "Setor/Setores" (cliente final)
export function useRotulos() {
  const { me } = useAuth();
  const singular = me?.rotulos.grupo_singular ?? "Cliente";
  const plural = me?.rotulos.grupo_plural ?? "Clientes";
  return { singular, plural, singularMin: singular.toLowerCase(), pluralMin: plural.toLowerCase() };
}

export const useSomenteLeitura = () => !!useAuth().me?.somente_leitura;

export const useSuperAdmin = () => useAuth().me?.usuario.papel === "SUPER_ADMIN";
