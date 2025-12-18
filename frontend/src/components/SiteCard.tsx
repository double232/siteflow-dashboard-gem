import { useState } from 'react';
import type { Site } from '../api/types';
import type { MonitorStatus } from '../api/types/health';
import type { SiteBackupStatus } from '../api/types/backups';
import { StatusBadge } from './StatusBadge';
import { StatusChecklist } from './StatusChecklist';
import { BackupBadge } from './BackupBadge';
import { QuickActions } from './QuickActions';
import { UptimeLine } from './UptimeLine';

interface Props {
  site: Site;
  healthStatus?: MonitorStatus;
  backupStatus?: SiteBackupStatus;
  onSiteAction: (siteName: string, action: 'start' | 'stop' | 'restart') => Promise<void>;
  onViewLogs: (siteName: string) => void;
  onDeprovision: (siteName: string) => void;
  onDeploy: (siteName: string) => void;
  onPull: (siteName: string) => void;
  isActionPending: boolean;
  isMobile?: boolean;
}

export const SiteCard = ({
  site,
  healthStatus,
  backupStatus,
  onSiteAction,
  onViewLogs,
  onDeprovision,
  onDeploy,
  onPull,
  isActionPending,
  isMobile = false,
}: Props) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const runningCount = site.containers.filter(c => c.status?.includes('Up')).length;
  const totalCount = site.containers.length;

  return (
    <div className={`site-card ${isMobile && isExpanded ? 'site-card--expanded' : ''}`}>
      <header className="site-card__header">
        <h3 className="site-card__name">{site.name}</h3>
        <StatusBadge status={site.status} />
      </header>

      <UptimeLine monitor={healthStatus} />

      <StatusChecklist site={site} healthStatus={healthStatus} />
      <BackupBadge backupStatus={backupStatus} />

      <div className={`site-card__info ${isMobile ? 'site-card__info--collapsible' : ''}`}>
        <div className="site-card__info-row">
          <span className="site-card__info-label">Domains:</span>
          <span className="site-card__info-value">
            {site.caddy_domains.length > 0
              ? site.caddy_domains.map((domain, idx) => (
                  <span key={domain}>
                    <a
                      href={`https://${domain.replace(/^https?:\/\//, '')}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="site-card__domain-link"
                    >
                      {domain}
                    </a>
                    {idx < site.caddy_domains.length - 1 && ', '}
                  </span>
                ))
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
          <span className="site-card__info-label">Ports:</span>
          <span className="site-card__info-value site-card__info-value--mono">
            {(() => {
              const ports = site.containers
                .flatMap(c => c.ports || [])
                .map(p => p.public ? `${p.public}->${p.private}` : p.private)
                .filter((v, i, a) => a.indexOf(v) === i);
              return ports.length > 0 ? ports.join(', ') : 'None';
            })()}
          </span>
        </div>
        <div className="site-card__info-row">
          <span className="site-card__info-label">Path:</span>
          <span className="site-card__info-value site-card__info-value--mono">
            {site.path}
          </span>
        </div>
      </div>

      {isMobile && (
        <button
          className="site-card__expand-btn"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          {isExpanded ? 'Hide Details' : 'Show Details'}
        </button>
      )}

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
