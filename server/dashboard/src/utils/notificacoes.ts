import { AlertTriangle, AlertOctagon, RadioTower, SignalLow, Siren, Unplug, VideoOff, WifiOff, Sparkles } from "lucide-react";
import { TipoNotificacao } from "../api/types";

// Cor e ícone por tipo (usados no pop-up de login e na aba Notificações)
export const ICONE_NOTIFICACAO: Record<TipoNotificacao, typeof AlertTriangle> = {
  LICENCA_UNM2000: AlertTriangle,
  BACKUP_FALHOU: AlertOctagon,
  AGENTE_OFFLINE: WifiOff,
  PERSONALIZADA: Sparkles,
  CAMERA_OFFLINE: VideoOff,
  ALARME: Siren,
  ANTENA_OFFLINE: RadioTower,
  ONU_OFFLINE: Unplug,
  SINAL_OPTICO: SignalLow,
};

export const COR_NOTIFICACAO: Record<TipoNotificacao, string> = {
  LICENCA_UNM2000: "var(--warn)",
  BACKUP_FALHOU: "var(--err)",
  AGENTE_OFFLINE: "var(--accent)",
  PERSONALIZADA: "var(--ok)",
  CAMERA_OFFLINE: "var(--err)",
  ALARME: "var(--err)",
  ANTENA_OFFLINE: "var(--err)",
  ONU_OFFLINE: "var(--err)",
  SINAL_OPTICO: "var(--warn)",
};

export const LABEL_NOTIFICACAO: Record<TipoNotificacao, string> = {
  LICENCA_UNM2000: "Licença da UNM2000",
  BACKUP_FALHOU: "Backup com falha",
  AGENTE_OFFLINE: "Agente offline",
  PERSONALIZADA: "Personalizada",
  CAMERA_OFFLINE: "Câmera offline",
  ALARME: "Alarme",
  ANTENA_OFFLINE: "Antena offline",
  ONU_OFFLINE: "ONU offline",
  SINAL_OPTICO: "Sinal óptico crítico",
};
