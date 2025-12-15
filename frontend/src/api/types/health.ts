export interface MonitorStatus {
  up: boolean;
  ping: number | null;
}

export interface HealthResponse {
  monitors: Record<string, MonitorStatus>;
}
