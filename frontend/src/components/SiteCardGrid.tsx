import type { Site } from '../api/types';
import type { HealthResponse } from '../api/types/health';
import { SiteCard } from './SiteCard';

interface Props {
  sites?: Site[];
  healthData?: HealthResponse;
  isLoading: boolean;
  onSiteAction: (siteName: string, action: 'start' | 'stop' | 'restart') => Promise<void>;
  onViewLogs: (siteName: string) => void;
  onDeprovision: (siteName: string) => void;
  onDeploy: (siteName: string) => void;
  onPull: (siteName: string) => void;
  isActionPending: boolean;
}

export const SiteCardGrid = ({
  sites,
  healthData,
  isLoading,
  onSiteAction,
  onViewLogs,
  onDeprovision,
  onDeploy,
  onPull,
  isActionPending,
}: Props) => {
  if (isLoading) {
    return (
      <div className="site-card-grid__loading">
        Loading sites...
      </div>
    );
  }

  if (!sites || sites.length === 0) {
    return (
      <div className="site-card-grid__empty">
        <h3>No sites found</h3>
        <p>Click "New Site" to provision your first site.</p>
      </div>
    );
  }

  // Helper to find health status by site name
  const getHealthStatus = (siteName: string) => {
    if (!healthData?.monitors) return undefined;
    // Try exact match first, then lowercase match
    return healthData.monitors[siteName] || healthData.monitors[siteName.toLowerCase()];
  };

  return (
    <div className="site-card-grid">
      {sites.map((site) => (
        <SiteCard
          key={site.name}
          site={site}
          healthStatus={getHealthStatus(site.name)}
          onSiteAction={onSiteAction}
          onViewLogs={onViewLogs}
          onDeprovision={onDeprovision}
          onDeploy={onDeploy}
          onPull={onPull}
          isActionPending={isActionPending}
        />
      ))}
    </div>
  );
};
