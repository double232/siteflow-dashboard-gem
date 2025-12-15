import type { Site } from '../api/types';
import type { MonitorStatus } from '../api/types/health';
import { StatusBadge } from './StatusBadge';
import { StatusChecklist } from './StatusChecklist';
import { QuickActions } from './QuickActions';

interface Props {
  site: Site;
  healthStatus?: MonitorStatus;
  onSiteAction: (siteName: string, action: 'start' | 'stop' | 'restart') => Promise<void>;
  onViewLogs: (siteName: string) => void;
  onDeprovision: (siteName: string) => void;
  onDeploy: (siteName: string) => void;
  onPull: (siteName: string) => void;
  isActionPending: boolean;
}

export const SiteCard = ({
  site,
  healthStatus,
  onSiteAction,
  onViewLogs,
  onDeprovision,
  onDeploy,
  onPull,
  isActionPending,
}: Props) => {
  const runningCount = site.containers.filter(c => c.status?.includes('Up')).length;
  const totalCount = site.containers.length;

  return (
    <div className="site-card">
      <header className="site-card__header">
        <h3 className="site-card__name">{site.name}</h3>
        <StatusBadge status={site.status} />
      </header>

      <StatusChecklist site={site} healthStatus={healthStatus} />

      <div className="site-card__info">
        <div className="site-card__info-row">
          <span className="site-card__info-label">Domains:</span>
          <span className="site-card__info-value">
            {site.caddy_domains.length > 0
              ? site.caddy_domains.join(', ')
              : 'None configured'}
          </span>
        </div>
        <div className="site-card__info-row">
          <span className="site-card__info-label">Containers:</span>
          <span className="site-card__info-value">
            {totalCount > 0
              ? `${runningCount}/${totalCount} running`
              : 'None'}
          </span>
        </div>
        <div className="site-card__info-row">
          <span className="site-card__info-label">Path:</span>
          <span className="site-card__info-value site-card__info-value--mono">
            {site.path}
          </span>
        </div>
      </div>

      <QuickActions
        siteName={site.name}
        onSiteAction={(action) => onSiteAction(site.name, action)}
        onViewLogs={() => onViewLogs(site.name)}
        onDeprovision={() => onDeprovision(site.name)}
        onDeploy={() => onDeploy(site.name)}
        onPull={() => onPull(site.name)}
        disabled={isActionPending}
      />
    </div>
  );
};
