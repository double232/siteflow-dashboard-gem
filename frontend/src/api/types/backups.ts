export type JobType = 'db' | 'uploads' | 'verify' | 'snapshot' | 'system' | 'site';
export type BackupStatus = 'ok' | 'warn' | 'fail';

// Backup action types
export interface BackupRequest {
  snapshot_tag?: string;
}

export interface RestoreRequest {
  snapshot_id: string;
  confirm: boolean;
}

export interface BackupActionResponse {
  status: 'success' | 'error';
  output: string;
  snapshot_id: string | null;
  duration_seconds: number;
}

export interface SnapshotInfo {
  id: string;
  short_id: string;
  time: string;
  hostname: string;
  tags: string[];
  paths: string[];
}

export interface SnapshotsResponse {
  snapshots: SnapshotInfo[];
  site?: string;
}

export interface SystemBackupStatus {
  last_system_backup: BackupRun | null;
  last_all_sites_backup: BackupRun | null;
  rpo_seconds_system: number | null;
  overall_status: BackupStatus;
}

export interface BackupRun {
  id: number;
  site: string;
  job_type: JobType;
  status: BackupStatus;
  started_at: string;
  ended_at: string;
  bytes_written: number | null;
  backup_id: string | null;
  repo: string | null;
  error: string | null;
  created_at: string;
}

export interface BackupRunsResponse {
  runs: BackupRun[];
  total: number;
  limit: number;
  offset: number;
}

export interface BackupThresholds {
  db_fresh_hours: number;
  uploads_fresh_hours: number;
  verify_fresh_days: number;
  snapshot_fresh_days: number;
}

export interface SiteBackupStatus {
  site: string;
  last_db_run: BackupRun | null;
  last_uploads_run: BackupRun | null;
  last_verify_run: BackupRun | null;
  last_snapshot_run: BackupRun | null;
  rpo_seconds_db: number | null;
  rpo_seconds_uploads: number | null;
  overall_status: BackupStatus;
}

export interface BackupSummaryResponse {
  sites: SiteBackupStatus[];
  thresholds: BackupThresholds;
}

export interface RestorePoint {
  site: string;
  job_type: JobType;
  timestamp: string;
  backup_id: string;
  repo: string | null;
}

export interface RestorePointsResponse {
  site: string;
  restore_points: RestorePoint[];
}

export interface BackupConfigResponse {
  thresholds: BackupThresholds;
  restic_repo: string;
}
