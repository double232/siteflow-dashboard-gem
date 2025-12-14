import type { Site } from '../api/types';
import { StatusBadge } from './StatusBadge';

interface Props {
  sites?: Site[];
  selected?: string;
  onSelect: (site: Site) => void;
}

export const SiteList = ({ sites, onSelect, selected }: Props) => {
  if (!sites?.length) {
    return <div className="panel">No sites found.</div>;
  }

  return (
    <div className="panel">
      <div className="panel__title">Sites ({sites.length})</div>
      <div className="site-list">
        {sites.map((site) => (
          <button
            type="button"
            key={site.name}
            className={`site-list__item ${selected === site.name ? 'site-list__item--active' : ''}`}
            onClick={() => onSelect(site)}
          >
            <div>
              <div className="site-list__name">{site.name}</div>
              <div className="site-list__meta">
                {site.caddy_domains.length} domains • {site.containers.length} containers
              </div>
            </div>
            <StatusBadge status={site.status} />
          </button>
        ))}
      </div>
    </div>
  );
};
