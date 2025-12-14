export interface PortMapping {
  private: string;
  public?: string | null;
  protocol?: string;
}

export interface ContainerStatus {
  name: string;
  status: string;
  state?: string | null;
  image?: string | null;
  ports: PortMapping[];
}

export interface SiteService {
  name: string;
  container_name?: string | null;
  image?: string | null;
  ports: PortMapping[];
  labels: Record<string, string>;
  environment: Record<string, string>;
}

export interface Site {
  name: string;
  path: string;
  compose_file: string;
  services: SiteService[];
  containers: ContainerStatus[];
  caddy_domains: string[];
  caddy_targets: string[];
  status: string;
}

export interface SitesResponse {
  sites: Site[];
  updated_at: number;
}

export interface NodeMetrics {
  cpu_percent: number;
  memory_percent: number;
  memory_usage_mb: number;
  memory_limit_mb: number;
}

export interface NodeBackupStatus {
  status: string;
  last_backup?: string | null;
  hours_since_backup?: number | null;
  backup_size_mb?: number | null;
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  status: string;
  meta: Record<string, unknown>;
  metrics?: NodeMetrics | null;
  backup?: NodeBackupStatus | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label?: string | null;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  nas_connected: boolean;
  nas_error?: string | null;
}

export interface ActionResponse {
  container: string;
  action: string;
  output: string;
}

export interface WebSocketMessage {
  type: string;
  data: unknown;
}

export interface ActionOutputMessage {
  container: string;
  action: string;
  status: 'started' | 'completed' | 'failed';
  output?: string;
  error?: string;
  duration_ms?: number;
}

// Route types for edge manipulation
export interface RouteRequest {
  domain: string;
  container: string;
  port: number;
}

export interface RouteResponse {
  success: boolean;
  message: string;
  domain?: string;
  container?: string;
}

export interface RouteInfo {
  domain: string;
  target: string;
  container?: string;
  port?: number;
}

export interface RoutesListResponse {
  routes: RouteInfo[];
}
