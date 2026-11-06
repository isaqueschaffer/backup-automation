import { AlertTriangle, AlertOctagon, WifiOff, Sparkles } from "lucide-react";
import { TipoNotificacao } from "../api/types";

// Cor e ícone por tipo (usados no pop-up de login e na aba Notificações)
export const ICONE_NOTIFICACAO: Record<TipoNotificacao, typeof AlertTriangle> = {
  LICENCA_UNM2000: AlertTriangle,
  BACKUP_FALHOU: AlertOctagon,
  AGENTE_OFFLINE: WifiOff,
  PERSONALIZADA: Sparkles,
};

export const COR_NOTIFICACAO: Record<TipoNotificacao, string> = {
  LICENCA_UNM2000: "var(--warn)",
  BACKUP_FALHOU: "var(--err)",
  AGENTE_OFFLINE: "var(--accent)",
  PERSONALIZADA: "var(--ok)",
};

export const LABEL_NOTIFICACAO: Record<TipoNotificacao, string> = {
  LICENCA_UNM2000: "Licença da UNM2000",
  BACKUP_FALHOU: "Backup com falha",
  AGENTE_OFFLINE: "Agente offline",
  PERSONALIZADA: "Personalizada",
};
