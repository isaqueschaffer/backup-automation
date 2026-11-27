import { useCallback, useState } from "react";
import { Machine, MaquinaSemBackup } from "../../api/types";
import { overallLevel, parseTelemetry } from "../Machines/MachineDetail/telemetry";

// Gravidade de cada máquina na Visão Geral: o que precisa de atenção vem primeiro.
// 0 offline · 1 sem backup desde o horário · 2 último backup com erro · 3 parcial · 4 saúde crítica · 5 ok · 6 desativada
export type Tom = "err" | "warn" | "ok" | "muted";

export interface Gravidade {
  nivel: number;
  rotulo: string;
  tom: Tom;
}

export function gravidadeDa(m: Machine, semBackup: Map<string, MaquinaSemBackup>): Gravidade {
  if (!m.active) return { nivel: 6, rotulo: "Desativada", tom: "muted" };
  if (!m.is_online) return { nivel: 0, rotulo: "Offline", tom: "err" };
  if (semBackup.has(m.id)) return { nivel: 1, rotulo: "Sem backup", tom: "err" };
  const st = (m.last_backup_status || "").toUpperCase();
  if (st === "ERROR") return { nivel: 2, rotulo: "Backup com erro", tom: "err" };
  if (st === "PARTIAL") return { nivel: 3, rotulo: "Backup parcial", tom: "warn" };
  const t = parseTelemetry(m.telemetry);
  if (t && overallLevel(t) === "err") return { nivel: 4, rotulo: "Saúde crítica", tom: "warn" };
  return { nivel: 5, rotulo: "OK", tom: "ok" };
}

// Atraso em texto curto ("3 h", "2 dias")
export function fmtAtraso(minutos: number): string {
  if (minutos < 60) return `${minutos} min`;
  const h = Math.floor(minutos / 60);
  if (h < 48) return `${h} h`;
  return `${Math.floor(h / 24)} dias`;
}

export type Ordem = "gravidade" | "personalizada";
export type Modo = "cards" | "lista";

interface Vista {
  ordem: Ordem;
  modo: Modo;
}

const CHAVE = "trilan.overview.vista.v1";

function carregar(): Vista {
  const padrao: Vista = { ordem: "gravidade", modo: "cards" };
  try {
    const bruto = JSON.parse(localStorage.getItem(CHAVE) || "null");
    if (!bruto || typeof bruto !== "object") return padrao;
    return {
      ordem: bruto.ordem === "personalizada" ? "personalizada" : "gravidade",
      modo: bruto.modo === "lista" ? "lista" : "cards",
    };
  } catch {
    return padrao;
  }
}

// Preferência de visualização (por navegador)
export function useVista() {
  const [vista, setVista] = useState<Vista>(carregar);
  const mudar = useCallback((parcial: Partial<Vista>) => {
    setVista(prev => {
      const prox = { ...prev, ...parcial };
      try {
        localStorage.setItem(CHAVE, JSON.stringify(prox));
      } catch {
        // sem armazenamento: vale só nesta aba
      }
      return prox;
    });
  }, []);
  return { ...vista, mudar };
}
