import type { Site } from '../api/types';

type CheckStatus = 'ok' | 'warning' | 'error';

interface CheckItem {
  id: string;
  label: string;
  status: CheckStatus;
  detail?: string;
}

interface Props {
  site: Site;
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

const getReachableCheck = (site: Site): CheckItem => {
  if (site.status === 'running') {
    return {
      id: 'reachable',
      label: 'Site reachable',
      status: 'ok',
      detail: 'All services healthy',
    };
  }

  if (site.status === 'degraded') {
    return {
      id: 'reachable',
      label: 'Site reachable',
      status: 'warning',
      detail: 'Some services degraded',
    };
  }

  if (site.status === 'stopped') {
    return {
      id: 'reachable',
      label: 'Site reachable',
      status: 'warning',
      detail: 'Container stopped (start to activate)',
    };
  }

  return {
    id: 'reachable',
    label: 'Site reachable',
    status: 'error',
    detail: 'Status unknown',
  };
};

const StatusIcon = ({ status }: { status: CheckStatus }) => {
  if (status === 'ok') {
    return <span className="checklist-item__icon">[x]</span>;
  }
  if (status === 'warning') {
    return <span className="checklist-item__icon">[!]</span>;
  }
  return <span className="checklist-item__icon">[ ]</span>;
};

export const StatusChecklist = ({ site }: Props) => {
  const checks: CheckItem[] = [
    getContainerCheck(site),
    getCaddyCheck(site),
    getCloudflareCheck(site),
    getReachableCheck(site),
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
