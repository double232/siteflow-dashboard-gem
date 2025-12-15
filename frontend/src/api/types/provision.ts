export type TemplateType = 'static' | 'node' | 'python' | 'wordpress';

export interface SiteTemplate {
  id: TemplateType;
  name: string;
  description: string;
  cms: string;
  stack: string;
  best_for: string[];
  required_services: string[];
}

export interface ProvisionRequest {
  name: string;
  template: TemplateType;
  domain?: string;
  environment?: Record<string, string>;
}

export interface DeprovisionRequest {
  name: string;
  remove_volumes?: boolean;
  remove_files?: boolean;
}

export interface ProvisionResponse {
  name: string;
  template: TemplateType;
  status: string;
  message: string;
  path?: string | null;
  domain?: string | null;
}

export interface DeprovisionResponse {
  name: string;
  status: string;
  message: string;
  volumes_removed: boolean;
  files_removed: boolean;
}

export interface TemplateListResponse {
  templates: SiteTemplate[];
}

export interface DetectRequest {
  git_url?: string;
  path?: string;
}

export interface DetectResponse {
  detected_type: TemplateType;
  confidence: 'high' | 'medium' | 'low';
  reason: string;
  files_checked: string[];
}
