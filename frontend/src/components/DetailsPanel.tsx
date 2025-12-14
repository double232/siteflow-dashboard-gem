import { useState } from 'react';

import type { Site } from '../api/types';
import { StatusBadge } from './StatusBadge';

interface Props {
  site?: Site;
  onAction: (container: string, action: 'start' | 'stop' | 'restart' | 'logs') => Promise<string>;
  onSiteAction: (site: string, action: 'start' | 'stop' | 'restart') => Promise<string>;
  isRunningAction: boolean;
}

export const DetailsPanel = ({ site, onAction, onSiteAction, isRunningAction }: Props) => {
  const [output, setOutput] = useState('');

  if (!site) {
    return (
      <div className="panel">
        <div className="panel__title">Select a site to inspect</div>
        <p>Click any site from the list or a node in the graph to inspect its topology.</p>
      </div>
    );
  }

  const handleAction = async (container: string, action: 'start' | 'stop' | 'restart' | 'logs') => {
    const result = await onAction(container, action);
    setOutput(result);
  };

  const handleSiteAction = async (action: 'start' | 'stop' | 'restart') => {
    const result = await onSiteAction(site.name, action);
    setOutput(result);
  };

  return (
    <div className="panel details-panel">
      <div className="panel__title">
        {site.name} <StatusBadge status={site.status} />
      </div>

      {/* Site-level actions */}
      <div className="details-panel__section site-actions">
        <div className="actions">
          <button
            type="button"
            disabled={isRunningAction}
            onClick={() => handleSiteAction('start')}
            className="action-start"
          >
            Start Site
          </button>
          <button
            type="button"
            disabled={isRunningAction}
            onClick={() => handleSiteAction('stop')}
            className="action-stop"
          >
            Stop Site
          </button>
          <button
            type="button"
            disabled={isRunningAction}
            onClick={() => handleSiteAction('restart')}
          >
            Restart Site
          </button>
        </div>
      </div>

      <div className="details-panel__section">
        <strong>Remote Path:</strong> {site.path}
      </div>
      <div className="details-panel__section">
        <strong>Domains ({site.caddy_domains.length}):</strong>
        {site.caddy_domains.length > 0 ? (
          <ul>
            {site.caddy_domains.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        ) : (
          <p className="no-data">No domains configured</p>
        )}
      </div>
      <div className="details-panel__section">
        <strong>Services ({site.services.length}):</strong>
        <ul className="service-list">
          {site.services.map((svc) => (
            <li key={svc.name}>
              <span className="service-name">{svc.container_name || svc.name}</span>
              <span className="service-image">{svc.image}</span>
            </li>
          ))}
        </ul>
      </div>
      {site.containers.length > 0 && (
        <div className="details-panel__section">
          <strong>Running Containers ({site.containers.length}):</strong>
          <ul className="container-actions">
            {site.containers.map((container) => (
              <li key={container.name}>
                <div>
                  <span className="container-name">{container.name}</span>
                  <span className="container-status">{container.status}</span>
                </div>
                <div className="actions">
                  {['start', 'stop', 'restart', 'logs'].map((action) => (
                    <button
                      type="button"
                      key={action}
                      disabled={isRunningAction}
                      onClick={() => handleAction(container.name, action as 'start' | 'stop' | 'restart' | 'logs')}
                    >
                      {action}
                    </button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {output && (
        <div className="details-panel__section">
          <strong>Last Action Output</strong>
          <pre className="output-window">{output}</pre>
        </div>
      )}
    </div>
  );
};
