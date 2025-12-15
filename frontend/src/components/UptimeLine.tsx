import type { MonitorStatus } from '../api/types/health';

interface Props {
  monitor?: MonitorStatus;
}

export const UptimeLine = ({ monitor }: Props) => {
  if (!monitor) {
    return (
      <div className="uptime-line uptime-line--unknown">
        <div className="uptime-line__bars">
          {Array.from({ length: 30 }).map((_, i) => (
            <div key={i} className="uptime-line__bar uptime-line__bar--unknown" />
          ))}
        </div>
        <span className="uptime-line__label">No data</span>
      </div>
    );
  }

  const { heartbeats, uptime, ping } = monitor;

  // Pad to 30 bars if we have fewer heartbeats
  const displayBars = heartbeats.length > 0
    ? heartbeats.slice(-30)
    : Array.from({ length: 30 }).map(() => ({ status: -1, time: '', ping: null }));

  // Pad from the left if we have fewer than 30
  while (displayBars.length < 30) {
    displayBars.unshift({ status: -1, time: '', ping: null });
  }

  const getBarClass = (status: number) => {
    switch (status) {
      case 1: return 'uptime-line__bar--up';
      case 0: return 'uptime-line__bar--down';
      case 2: return 'uptime-line__bar--pending';
      default: return 'uptime-line__bar--unknown';
    }
  };

  const getUptimeClass = () => {
    if (uptime >= 99) return 'uptime-line__label--excellent';
    if (uptime >= 95) return 'uptime-line__label--good';
    if (uptime >= 90) return 'uptime-line__label--warning';
    return 'uptime-line__label--poor';
  };

  return (
    <div className="uptime-line">
      <div className="uptime-line__bars">
        {displayBars.map((hb, i) => (
          <div
            key={i}
            className={`uptime-line__bar ${getBarClass(hb.status)}`}
            title={hb.time ? `${hb.time}${hb.ping ? ` - ${hb.ping}ms` : ''}` : 'No data'}
          />
        ))}
      </div>
      <div className="uptime-line__info">
        <span className={`uptime-line__label ${getUptimeClass()}`}>
          {uptime.toFixed(1)}%
        </span>
        {ping !== null && (
          <span className="uptime-line__ping">{ping}ms</span>
        )}
      </div>
    </div>
  );
};
