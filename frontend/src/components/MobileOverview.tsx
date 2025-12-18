import type { Site } from '../api/types';
import type { HealthResponse, MonitorStatus } from '../api/types/health';
import type { BackupSummaryResponse } from '../api/types/backups';

interface MonitorWithName extends MonitorStatus {
  name: string;
}

interface Props {
  sites?: Site[];
  healthData?: HealthResponse;
  backupData?: BackupSummaryResponse;
}

export const MobileOverview = ({ sites, healthData, backupData }: Props) => {
  // Calculate overall stats
  const totalSites = sites?.length || 0;
  const runningSites = sites?.filter(s => s.status === 'running').length || 0;
  const stoppedSites = totalSites - runningSites;

  // Calculate uptime stats from health data
  const monitorsWithNames: MonitorWithName[] = healthData?.monitors
    ? Object.entries(healthData.monitors).map(([name, status]) => ({ ...status, name }))
    : [];
  const uptimeValues = monitorsWithNames
    .filter(m => m.uptime !== undefined)
    .map(m => m.uptime || 0);
  const avgUptime = uptimeValues.length > 0
    ? uptimeValues.reduce((a, b) => a + b, 0) / uptimeValues.length
    : null;

  // Find sites with issues (down or low uptime)
  const sitesWithIssues = monitorsWithNames.filter(m => {
    const isDown = m.heartbeats?.some(h => h.status === 0);
    const lowUptime = m.uptime !== undefined && m.uptime < 99;
    return isDown || lowUptime;
  });

  // Backup status
  const backupSites = backupData?.sites || [];
  const backupsOk = backupSites.filter(b => b.overall_status === 'ok').length;
  const backupsWarn = backupSites.filter(b => b.overall_status === 'warn' || b.overall_status === 'fail').length;

  // Determine overall health status
  const getHealthStatus = () => {
    if (stoppedSites > 0 || sitesWithIssues.length > 0) return 'warning';
    if (avgUptime !== null && avgUptime < 99) return 'warning';
    if (backupsWarn > 0) return 'warning';
    return 'healthy';
  };

  const healthStatus = getHealthStatus();

  return (
    <div className="mobile-overview">
      <div className="mobile-overview__header">
        <div className={`mobile-overview__status mobile-overview__status--${healthStatus}`}>
          <span className="mobile-overview__status-icon">
            {healthStatus === 'healthy' ? '[OK]' : '[!]'}
          </span>
          <span className="mobile-overview__status-text">
            {healthStatus === 'healthy' ? 'All Systems Operational' : 'Issues Detected'}
          </span>
        </div>
        {avgUptime !== null && (
          <div className="mobile-overview__uptime">
            <span className="mobile-overview__uptime-value">{avgUptime.toFixed(2)}%</span>
            <span className="mobile-overview__uptime-label">Avg Uptime</span>
          </div>
        )}
      </div>

      <div className="mobile-overview__stats">
        <div className="mobile-overview__stat">
          <span className="mobile-overview__stat-value">{runningSites}</span>
          <span className="mobile-overview__stat-label">Running</span>
        </div>
        <div className="mobile-overview__stat mobile-overview__stat--separator">
          <span className="mobile-overview__stat-value">{stoppedSites}</span>
          <span className="mobile-overview__stat-label">Stopped</span>
        </div>
        <div className="mobile-overview__stat mobile-overview__stat--separator">
          <span className="mobile-overview__stat-value">{backupsOk}</span>
          <span className="mobile-overview__stat-label">Backups OK</span>
        </div>
        {backupsWarn > 0 && (
          <div className="mobile-overview__stat mobile-overview__stat--separator mobile-overview__stat--warn">
            <span className="mobile-overview__stat-value">{backupsWarn}</span>
            <span className="mobile-overview__stat-label">Backup Issues</span>
          </div>
        )}
      </div>

      {sitesWithIssues.length > 0 && (
        <div className="mobile-overview__alerts">
          <div className="mobile-overview__alerts-title">Recent Issues</div>
          {sitesWithIssues.slice(0, 3).map((monitor, idx) => (
            <div key={idx} className="mobile-overview__alert">
              <span className="mobile-overview__alert-icon">[!]</span>
              <span className="mobile-overview__alert-name">{monitor.name || 'Unknown'}</span>
              <span className="mobile-overview__alert-detail">
                {monitor.uptime !== undefined ? `${monitor.uptime.toFixed(1)}% uptime` : 'Down'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
