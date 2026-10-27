import { Network, Phone, Video, Wifi, WifiOff } from "lucide-react";

// Ordem em que os grupos aparecem na tela; tipos fora da lista vão ao final
export const EQ_TIPO_ORDEM = ["NVR", "DIGIFORT", "DEFENSE", "OLT", "ONU", "MIKROTIK", "PABX", "MIXED"];

export const EQ_TIPO_ROTULO: Record<string, string> = {
  NVR: "NVR / DVR",
  DIGIFORT: "Digifort",
  DEFENSE: "Defense IA",
  OLT: "OLT",
  ONU: "ONU",
  MIKROTIK: "Mikrotik",
  PABX: "PABX",
  MIXED: "Misto",
};

export function eqRotulo(tipo: string): string {
  return EQ_TIPO_ROTULO[tipo] || tipo;
}

export function eqIcone(tipo: string, size = 18): React.ReactNode {
  const m: Record<string, React.ReactNode> = {
    NVR: <Video size={size} />,
    OLT: <Wifi size={size} />,
    ONU: <WifiOff size={size} />,
    PABX: <Phone size={size} />,
    MIKROTIK: <Network size={size} />,
    DIGIFORT: <Video size={size} />,
    DEFENSE: <Video size={size} />,
  };
  return m[tipo] || <Video size={size} />;
}

export function eqCor(tipo: string): string {
  const m: Record<string, string> = {
    NVR: "var(--primary)",
    OLT: "#10b981",
    ONU: "#f59e0b",
    PABX: "#8b5cf6",
    MIKROTIK: "#3b82f6",
    DIGIFORT: "#f43f5e",
    DEFENSE: "#ec4899",
  };
  return m[tipo] || "var(--text-muted)";
}
