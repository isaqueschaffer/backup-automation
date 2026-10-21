// Telemetria enviada pelo agente no ping: leitura tolerante a agentes antigos, níveis de uso e formatação
export const WARN_PCT = 75;
export const CRIT_PCT = 90;
export type HealthLevel = "ok" | "warn" | "err";

export interface TelemetryDisk {
  device: string;
  fstype: string | null;
  percent: number | null;
  totalGb: number | null;
  usedGb: number | null;
  freeGb: number | null;
}

export interface TelemetryNet {
  name: string;
  sentMbps: number;
  recvMbps: number;
  virtual: boolean;
}

export interface TelemetryGpu {
  name: string;
  percent: number | null;
  memUsedMb: number | null;
  memTotalMb: number | null;
}

export interface Telemetry {
  cpuPercent: number | null;
  ramPercent: number | null;
  ramUsedGb: number | null;
  ramTotalGb: number | null;
  disks: TelemetryDisk[];
  networks: TelemetryNet[];
  gpu: TelemetryGpu | null;
}

export const LEVEL_COLOR: Record<HealthLevel, string> = {
  ok: "var(--ok)",
  warn: "var(--warn)",
  err: "var(--err)",
};

export const LEVEL_LABEL: Record<HealthLevel, string> = {
  ok: "Saudável",
  warn: "Atenção",
  err: "Crítico",
};

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function isVirtualNic(name: string): boolean {
  return /vEthernet|VMware|VirtualBox|Hyper-V|Loopback|isatap|Teredo|Bluetooth|TAP-|WireGuard|Npcap|ZeroTier|Tailscale|Docker|WSL/i.test(name);
}

export function parseTelemetry(raw: Record<string, any> | null | undefined): Telemetry | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;

  const disks: TelemetryDisk[] = [];
  if (Array.isArray(raw.disks) && raw.disks.length > 0) {
    raw.disks.forEach((d, i) => {
      if (!d || typeof d !== "object") return;
      const rawDevice = (typeof d.device === "string" && d.device)
        || (typeof d.mountpoint === "string" && d.mountpoint)
        || `Disco ${i + 1}`;
      const device = rawDevice.replace(/\\+$/, "");
      const fstype = typeof d.fstype === "string" && d.fstype.trim().length > 0 ? d.fstype.trim() : null;
      const percent = num(d.percent);
      const totalGb = num(d.total_gb);
      const freeGb = num(d.free_gb);
      const usedGb = num(d.used_gb) ?? (totalGb !== null && freeGb !== null ? totalGb - freeGb : null);
      disks.push({ device, fstype, percent, totalGb, usedGb, freeGb });
    });
  } else if (num(raw.disk_percent) !== null || num(raw.disk_free_gb) !== null) {
    const totalGb = num(raw.disk_total_gb);
    const freeGb = num(raw.disk_free_gb);
    const usedGb = totalGb !== null && freeGb !== null ? totalGb - freeGb : null;
    disks.push({
      device: "C:",
      fstype: null,
      percent: num(raw.disk_percent),
      totalGb,
      freeGb,
      usedGb,
    });
  }

  const networks: TelemetryNet[] = [];
  if (Array.isArray(raw.networks)) {
    for (const n of raw.networks) {
      if (n && typeof n === "object" && typeof n.name === "string" && n.name.trim().length > 0) {
        networks.push({
          name: n.name.trim(),
          sentMbps: num(n.mbps_sent) ?? 0,
          recvMbps: num(n.mbps_recv) ?? 0,
          virtual: isVirtualNic(n.name),
        });
      }
    }
    networks.sort((a, b) => {
      if (a.virtual !== b.virtual) {
        return a.virtual ? 1 : -1;
      }
      const trafficA = a.sentMbps + a.recvMbps;
      const trafficB = b.sentMbps + b.recvMbps;
      return trafficB - trafficA;
    });
  }

  let gpu: TelemetryGpu | null = null;
  if (typeof raw.gpu_name === "string" && raw.gpu_name.trim().length > 0) {
    gpu = {
      name: raw.gpu_name.trim(),
      percent: num(raw.gpu_percent),
      memUsedMb: num(raw.gpu_memory_used),
      memTotalMb: num(raw.gpu_memory_total),
    };
  }

  const cpuPercent = num(raw.cpu_percent);
  const ramPercent = num(raw.ram_percent);
  const ramUsedGb = num(raw.ram_used_gb);
  const ramTotalGb = num(raw.ram_total_gb);

  if (cpuPercent === null && ramPercent === null && disks.length === 0 && networks.length === 0 && !gpu) {
    return null;
  }

  return {
    cpuPercent,
    ramPercent,
    ramUsedGb,
    ramTotalGb,
    disks,
    networks,
    gpu,
  };
}

export function levelOf(p: number | null): HealthLevel | null {
  if (p === null || !Number.isFinite(p)) return null;
  if (p > CRIT_PCT) return "err";
  if (p > WARN_PCT) return "warn";
  return "ok";
}

export function overallLevel(t: Telemetry): HealthLevel | null {
  const levels: HealthLevel[] = [];

  const cpu = levelOf(t.cpuPercent);
  if (cpu) levels.push(cpu);

  const ram = levelOf(t.ramPercent);
  if (ram) levels.push(ram);

  for (const d of t.disks) {
    const l = levelOf(d.percent);
    if (l) levels.push(l);
  }

  if (t.gpu) {
    const gpuL = levelOf(t.gpu.percent);
    if (gpuL) levels.push(gpuL);
  }

  if (levels.length === 0) return null;
  if (levels.includes("err")) return "err";
  if (levels.includes("warn")) return "warn";
  return "ok";
}

export function worstDisk(disks: TelemetryDisk[]): TelemetryDisk | null {
  if (disks.length === 0) return null;
  let best: TelemetryDisk | null = null;
  for (const d of disks) {
    if (d.percent !== null) {
      if (!best || (best.percent !== null && d.percent > best.percent)) {
        best = d;
      }
    }
  }
  return best ?? disks[0];
}

export function fmtPct(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  return `${Math.round(v)}%`;
}

export function fmtGb(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  if (v >= 1024) {
    return `${(v / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} TB`;
  }
  return `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} GB`;
}

export function fmtMb(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  if (v >= 1024) {
    return `${(v / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} GB`;
  }
  return `${Math.round(v)} MB`;
}

export function fmtMbps(v: number): string {
  if (!Number.isFinite(v) || v <= 0) return "0 Mbps";
  if (v >= 1000) {
    return `${(v / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} Gbps`;
  }
  if (v >= 1) {
    return `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} Mbps`;
  }
  return `${Math.round(v * 1000)} kbps`;
}

export function fmtAgo(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 5) return "agora";
  if (s < 60) return `há ${s} s`;
  if (s < 3600) return `há ${Math.floor(s / 60)} min`;
  if (s < 86400) return `há ${Math.floor(s / 3600)} h`;
  return `há ${Math.floor(s / 86400)} d`;
}
