export type TipoEquipamento = "NVR" | "OLT" | "ONU" | "PABX" | "MIKROTIK" | "DIGIFORT" | "DEFENSE" | "CAMERA";

export interface NVR {
  id: string;
  client_id: string;
  tipo: TipoEquipamento;
  name: string;
  ip: string;
  username: string;
  config_extra?: Record<string, unknown> | null;
  last_recording_status?: any;
  active: boolean;
}

// Alias semântico
export type Equipamento = NVR;

export interface Client {
  id: string;
  name: string;
  api_key_prefix: string;
  backup_hour: number;
  backup_minute: number;
  email_to: string[];
  active: boolean;
  last_seen: string | null;
  last_backup_at: string | null;
  last_backup_status: string | null;
  created_at: string;
  nvr_count: number;
  restart_requested?: boolean;
  backup_requested?: boolean;
  telemetry?: Record<string, any> | null;
  api_key?: string; // only on create/rotate
  // Campos calculados no servidor (fonte única da verdade para status online)
  is_online?: boolean;
  current_server_time?: string;
  group_id?: string | null;
  group_name?: string | null;
  queue_order?: number;
}

export interface NVRResult {
  nome: string;
  status: string;
  tipo?: TipoEquipamento;
}

export interface Backup {
  id: string;
  client_id: string;
  client_name: string | null;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  nvr_results: NVRResult[] | null;
  zip_filename: string | null;
  zip_size: number | null;
  email_sent: boolean;
  trigger: string;
  created_at: string | null;
}

export interface PaginatedBackups {
  items: Backup[];
  total: number;
  page: number;
  pages: number;
}

export interface Stats {
  total_clients: number;
  active_clients: number;
  backups_today: number;
  backups_ok: number;
  backups_error: number;
}

export interface Settings {
  smtp_server: string | null;
  smtp_port: string | null;
  smtp_email: string | null;
  retention_days: string | null;
}

export interface ClientGroup {
  id: string;
  name: string;
  description: string | null;
  active: boolean;
  backup_hour: number;
  backup_minute: number;
  created_at: string;
  agents_total: number;
  agents_online: number;
  health: "ALL_OK" | "PARTIAL" | "ALL_ERROR" | "NO_DATA";
  last_backup_at: string | null;
  queue_active: boolean;
  clients: Client[];
}

