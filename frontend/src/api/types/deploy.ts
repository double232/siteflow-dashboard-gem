export interface GitDeployRequest {
  site: string;
  repo_url: string;
  branch?: string;
}

export interface PullRequest {
  site: string;
}

export interface DeployResponse {
  site: string;
  status: 'success' | 'partial' | 'error';
  output: string;
  repo_url: string | null;
}

export interface DeployStatus {
  site: string;
  configured: boolean;
  repo_url: string | null;
  branch: string | null;
  last_commit: string | null;
}
