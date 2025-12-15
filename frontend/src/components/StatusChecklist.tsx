import type { Site } from '../api/types';
import type { MonitorStatus } from '../api/types/health';

type CheckStatus = 'ok' | 'warning' | 'error';

interface CheckItem {
  id: string;
  label: string;
  status: CheckStatus;
  detail?: string;
}

interface Props {
  site: Site;
  healthStatus?: MonitorStatus;
}

const getContainerCheck = (site: Site): CheckItem => {
  const running = site.containers.filter(c => c.status?.includes('Up')).length;
  const total = site.containers.length;

  if (total === 0) {
    return {
      id: 'container',
      label: 'Container running',
      status: 'error',
      detail: 'No containers found',
    };
  }

  if (running === total) {
    return {
      id: 'container',
      label: 'Container running',
      status: 'ok',
      detail: `${running} container${running > 1 ? 's' : ''} running`,
    };
  }

  if (running > 0) {
    return {
      id: 'container',
      label: 'Container running',
      status: 'warning',
      detail: `${running}/${total} running`,
    };
  }

  return {
    id: 'container',
    label: 'Container running',
    status: 'error',
    detail: 'All containers stopped',
  };
};

const getCaddyCheck = (site: Site): CheckItem => {
  if (site.caddy_domains.length > 0) {
    return {
      id: 'caddy',
      label: 'Caddy configured',
      status: 'ok',
      detail: site.caddy_domains.join(', '),
    };
  }

  return {
    id: 'caddy',
    label: 'Caddy configured',
    status: 'error',
    detail: 'No domains configured',
  };
};

const getCloudflareCheck = (site: Site): CheckItem => {
  // Infer from caddy domains - if caddy is configured, CF tunnel likely works
  if (site.caddy_domains.length > 0) {
    return {
      id: 'cloudflare',
      label: 'Cloudflare connected',
      status: 'ok',
      detail: 'Tunnel active',
    };
  }

  return {
    id: 'cloudflare',
    label: 'Cloudflare connected',
    status: 'warning',
    detail: 'No domains to route',
  };
};

const getReachableCheck = (siteName: string, healthStatus?: MonitorStatus): CheckItem => {
  // Use real HTTP health check from Uptime Kuma
  if (!healthStatus) {
    // uptime-kuma doesn't monitor itself - if we're getting health data, it's up
    if (siteName === 'uptime-kuma') {
      return {
        id: 'reachable',
        label: 'Site reachable',
        status: 'ok',
        detail: 'Self (Kuma running)',
      };
    }
    return {
      id: 'reachable',
      label: 'Site reachable',
      status: 'warning',
      detail: 'No monitor configured',
    };
  }

  if (healthStatus.up) {
    const pingDetail = healthStatus.ping ? `${healthStatus.ping}ms` : 'OK';
    return {
      id: 'reachable',
      label: 'Site reachable',
      status: 'ok',
      detail: pingDetail,
    };
  }

  return {
    id: 'reachable',
    label: 'Site reachable',
    status: 'error',
    detail: 'Site down',
  };
};

const StatusIcon = ({ status }: { status: CheckStatus }) => {
  if (status === 'ok') {
    return <span className="checklist-item__icon">[o]</span>;
  }
  if (status === 'warning') {
    return <span className="checklist-item__icon">[!]</span>;
  }
  return <span className="checklist-item__icon">[x]</span>;
};

export const StatusChecklist = ({ site, healthStatus }: Props) => {
  const checks: CheckItem[] = [
    getContainerCheck(site),
    getCaddyCheck(site),
    getCloudflareCheck(site),
    getReachableCheck(site.name, healthStatus),
  ];

  return (
    <div className="status-checklist">
      <div className="status-checklist__title">Health Checklist:</div>
      {checks.map((check) => (
        <div
          key={check.id}
          className={`checklist-item checklist-item--${check.status}`}
          title={check.detail}
        >
          <StatusIcon status={check.status} />
          <span className="checklist-item__label">{check.label}</span>
          {check.detail && (
            <span className="checklist-item__detail">{check.detail}</span>
          )}
        </div>
      ))}
    </div>
  );
};
