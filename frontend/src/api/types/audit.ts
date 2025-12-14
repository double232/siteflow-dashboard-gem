export interface AuditLogEntry {
  id: number;
  timestamp: string;
  action_type: string;
  target_type: string;
  target_name: string;
  status: string;
  output?: string | null;
  error_message?: string | null;
  metadata: Record<string, unknown>;
  duration_ms?: number | null;
}

export interface AuditLogFilter {
  action_type?: string;
  target_type?: string;
  target_name?: string;
  status?: string;
  start_date?: string;
  end_date?: string;
}

export interface AuditLogResponse {
  logs: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export type ActionType =
  | 'container_start'
  | 'container_stop'
  | 'container_restart'
  | 'container_logs'
  | 'caddy_reload'
  | 'site_provision'
  | 'site_deprovision';

export type TargetType = 'container' | 'site' | 'caddy' | 'system';

export type ActionStatus = 'success' | 'failure' | 'pending';
