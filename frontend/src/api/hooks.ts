import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from './client';
import type { ActionResponse, GraphResponse, SitesResponse } from './types';
import type { AuditLogResponse } from './types/audit';
import type {
  DeprovisionRequest,
  DeprovisionResponse,
  ProvisionRequest,
  ProvisionResponse,
  TemplateListResponse,
} from './types/provision';
import type {
  DeployResponse,
  DeployStatus,
  GitDeployRequest,
  PullRequest,
} from './types/deploy';
import type { RouteRequest, RouteResponse, RoutesListResponse } from './types';

interface UseQueryOptions {
  useWebSocket?: boolean;
}

export const useSites = (options?: UseQueryOptions) =>
  useQuery<SitesResponse>({
    queryKey: ['sites'],
    queryFn: async () => {
      const { data } = await apiClient.get<SitesResponse>('/api/sites/');
      return data;
    },
    refetchInterval: options?.useWebSocket ? false : 60000,
  });

export const useGraph = (options?: UseQueryOptions) =>
  useQuery<GraphResponse>({
    queryKey: ['graph'],
    queryFn: async () => {
      const { data } = await apiClient.get<GraphResponse>('/api/graph/');
      return data;
    },
    refetchInterval: options?.useWebSocket ? false : 60000,
  });

export const useContainerAction = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      container,
      action,
    }: {
      container: string;
      action: 'start' | 'stop' | 'restart' | 'logs';
    }) => {
      const { data } = await apiClient.post<ActionResponse>(
        `/api/sites/containers/${container}/${action}`,
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sites'] });
      queryClient.invalidateQueries({ queryKey: ['graph'] });
    },
  });
};

export const useSiteAction = () => {
  return useMutation({
    mutationFn: async ({
      site,
      action,
    }: {
      site: string;
      action: 'start' | 'stop' | 'restart';
    }) => {
      const { data } = await apiClient.post<ActionResponse>(
        `/api/sites/${site}/${action}`,
      );
      return data;
    },
    // WebSocket handles live updates - no cache invalidation needed
  });
};

export const useReloadCaddy = () =>
  useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post<{ message: string }>(
        '/api/sites/caddy/reload/',
      );
      return data.message;
    },
  });

// Audit hooks
interface AuditLogParams {
  page?: number;
  page_size?: number;
  action_type?: string;
  target_type?: string;
  target_name?: string;
  status?: string;
}

export const useAuditLogs = (params?: AuditLogParams) =>
  useQuery<AuditLogResponse>({
    queryKey: ['audit-logs', params],
    queryFn: async () => {
      const { data } = await apiClient.get<AuditLogResponse>('/api/audit/logs/', {
        params,
      });
      return data;
    },
  });

// Provision hooks
export const useTemplates = () =>
  useQuery<TemplateListResponse>({
    queryKey: ['templates'],
    queryFn: async () => {
      const { data } = await apiClient.get<TemplateListResponse>(
        '/api/provision/templates',
      );
      return data;
    },
    staleTime: 5 * 60 * 1000, // Templates rarely change
  });

export const useProvisionSite = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (request: ProvisionRequest) => {
      const { data } = await apiClient.post<ProvisionResponse>(
        '/api/provision/',
        request,
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sites'] });
      queryClient.invalidateQueries({ queryKey: ['graph'] });
    },
  });
};

export const useDeprovisionSite = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (request: DeprovisionRequest) => {
      const { data } = await apiClient.delete<DeprovisionResponse>(
        '/api/provision/',
        { data: request },
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sites'] });
      queryClient.invalidateQueries({ queryKey: ['graph'] });
    },
  });
};

// Route hooks for edge manipulation
export const useRoutes = () =>
  useQuery<RoutesListResponse>({
    queryKey: ['routes'],
    queryFn: async () => {
      const { data } = await apiClient.get<RoutesListResponse>('/api/routes/');
      return data;
    },
  });

export const useAddRoute = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (request: RouteRequest) => {
      const { data } = await apiClient.post<RouteResponse>(
        '/api/routes/',
        request,
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['routes'] });
      queryClient.invalidateQueries({ queryKey: ['graph'] });
      queryClient.invalidateQueries({ queryKey: ['sites'] });
    },
  });
};

export const useRemoveRoute = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (domain: string) => {
      const { data } = await apiClient.delete<RouteResponse>(
        '/api/routes/',
        { params: { domain } },
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['routes'] });
      queryClient.invalidateQueries({ queryKey: ['graph'] });
      queryClient.invalidateQueries({ queryKey: ['sites'] });
    },
  });
};

// Deploy hooks
export const useDeployFromGitHub = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (request: GitDeployRequest) => {
      const { data } = await apiClient.post<DeployResponse>(
        '/api/deploy/github',
        request,
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sites'] });
      queryClient.invalidateQueries({ queryKey: ['deploy-status'] });
    },
  });
};

export const usePullLatest = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (request: PullRequest) => {
      const { data } = await apiClient.post<DeployResponse>(
        '/api/deploy/pull',
        request,
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sites'] });
      queryClient.invalidateQueries({ queryKey: ['deploy-status'] });
    },
  });
};

export const useDeployStatus = (site: string) =>
  useQuery<DeployStatus>({
    queryKey: ['deploy-status', site],
    queryFn: async () => {
      const { data } = await apiClient.get<DeployStatus>(
        `/api/deploy/${site}/status`,
      );
      return data;
    },
    enabled: !!site,
  });
