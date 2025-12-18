import type { Site } from '../api/types';
import type { HealthResponse } from '../api/types/health';
import type { BackupSummaryResponse } from '../api/types/backups';

export type SiteFilter = 'all' | 'issues' | 'stopped' | 'backup_warnings';

interface FilterCounts {
  all: number;
  issues: number;
  stopped: number;
  backup_warnings: number;
}

interface Props {
  activeFilter: SiteFilter;
  onFilterChange: (filter: SiteFilter) => void;
  sites?: Site[];
  healthData?: HealthResponse;
  backupData?: BackupSummaryResponse;
}

export const computeFilterCounts = (
  sites?: Site[],
  healthData?: HealthResponse,
  backupData?: BackupSummaryResponse
): FilterCounts => {
  if (!sites) {
    return { all: 0, issues: 0, stopped: 0, backup_warnings: 0 };
  }

  let issues = 0;
  let stopped = 0;
  let backup_warnings = 0;

  for (const site of sites) {
    // Check stopped
    if (site.status === 'stopped' || site.status === 'degraded') {
      stopped++;
    }

    // Check health issues
    const monitor = healthData?.monitors?.[site.name] || healthData?.monitors?.[site.name.toLowerCase()];
    if (monitor) {
      const isDown = monitor.heartbeats?.some(h => h.status === 0);
      const lowUptime = monitor.uptime !== undefined && monitor.uptime < 99;
      if (isDown || lowUptime) {
        issues++;
      }
    }

    // Check backup warnings
    const backupStatus = backupData?.sites?.find(
      b => b.site === site.name || b.site === site.name.toLowerCase()
    );
    if (backupStatus && (backupStatus.overall_status === 'warn' || backupStatus.overall_status === 'fail')) {
      backup_warnings++;
    }
  }

  return {
    all: sites.length,
    issues,
    stopped,
    backup_warnings,
  };
};

export const filterSites = (
  sites: Site[] | undefined,
  filter: SiteFilter,
  healthData?: HealthResponse,
  backupData?: BackupSummaryResponse
): Site[] | undefined => {
  if (!sites || filter === 'all') {
    return sites;
  }

  return sites.filter(site => {
    if (filter === 'stopped') {
      return site.status === 'stopped' || site.status === 'degraded';
    }

    if (filter === 'issues') {
      const monitor = healthData?.monitors?.[site.name] || healthData?.monitors?.[site.name.toLowerCase()];
      if (!monitor) return false;
      const isDown = monitor.heartbeats?.some(h => h.status === 0);
      const lowUptime = monitor.uptime !== undefined && monitor.uptime < 99;
      return isDown || lowUptime;
    }

    if (filter === 'backup_warnings') {
      const backupStatus = backupData?.sites?.find(
        b => b.site === site.name || b.site === site.name.toLowerCase()
      );
      return backupStatus && (backupStatus.overall_status === 'warn' || backupStatus.overall_status === 'fail');
    }

    return true;
  });
};

export const SiteFilterBar = ({
  activeFilter,
  onFilterChange,
  sites,
  healthData,
  backupData,
}: Props) => {
  const counts = computeFilterCounts(sites, healthData, backupData);

  const filters: { key: SiteFilter; label: string; count: number }[] = [
    { key: 'all', label: 'All', count: counts.all },
    { key: 'issues', label: 'Issues', count: counts.issues },
    { key: 'stopped', label: 'Stopped', count: counts.stopped },
    { key: 'backup_warnings', label: 'Backups', count: counts.backup_warnings },
  ];

  return (
    <div className="site-filter-bar">
      {filters.map(({ key, label, count }) => (
        <button
          key={key}
          type="button"
          className={`site-filter-bar__btn ${activeFilter === key ? 'site-filter-bar__btn--active' : ''} ${
            key !== 'all' && count > 0 ? 'site-filter-bar__btn--has-items' : ''
          }`}
          onClick={() => onFilterChange(key)}
        >
          <span className="site-filter-bar__label">{label}</span>
          {count > 0 && (
            <span className={`site-filter-bar__count ${key !== 'all' && count > 0 ? 'site-filter-bar__count--warn' : ''}`}>
              {count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
};
