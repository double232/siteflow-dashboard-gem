import type { Site } from '../api/types';
import { SiteCard } from './SiteCard';

interface Props {
  sites?: Site[];
  isLoading: boolean;
  onSiteAction: (siteName: string, action: 'start' | 'stop' | 'restart') => Promise<void>;
  onViewLogs: (siteName: string) => void;
  onDeprovision: (siteName: string) => void;
  isActionPending: boolean;
}

export const SiteCardGrid = ({
  sites,
  isLoading,
  onSiteAction,
  onViewLogs,
  onDeprovision,
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

  return (
    <div className="site-card-grid">
      {sites.map((site) => (
        <SiteCard
          key={site.name}
          site={site}
          onSiteAction={onSiteAction}
          onViewLogs={onViewLogs}
          onDeprovision={onDeprovision}
          isActionPending={isActionPending}
        />
      ))}
    </div>
  );
};
