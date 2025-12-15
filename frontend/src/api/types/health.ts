export interface HeartbeatEntry {
  status: number; // 0=down, 1=up, 2=pending
  time: string;
  ping: number | null;
}

export interface MonitorStatus {
  up: boolean;
  ping: number | null;
  uptime: number; // Percentage 0-100
  heartbeats: HeartbeatEntry[]; // Last N heartbeats for visualization
}

export interface HealthResponse {
  monitors: Record<string, MonitorStatus>;
}
