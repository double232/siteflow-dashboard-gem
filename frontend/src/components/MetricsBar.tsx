import type { NodeMetrics } from '../api/types';

interface MetricsBarProps {
  metrics: NodeMetrics;
  compact?: boolean;
}

export const MetricsBar = ({ metrics, compact = false }: MetricsBarProps) => {
  const cpuColor = metrics.cpu_percent > 80 ? '#ef4444' : metrics.cpu_percent > 50 ? '#f59e0b' : '#22c55e';
  const memColor = metrics.memory_percent > 80 ? '#ef4444' : metrics.memory_percent > 50 ? '#f59e0b' : '#22c55e';

  if (compact) {
    return (
      <div className="metrics-bar metrics-bar--compact">
        <span className="metrics-bar__item" style={{ color: cpuColor }}>
          CPU: {metrics.cpu_percent.toFixed(1)}%
        </span>
        <span className="metrics-bar__item" style={{ color: memColor }}>
          MEM: {metrics.memory_percent.toFixed(1)}%
        </span>
      </div>
    );
  }

  return (
    <div className="metrics-bar">
      <div className="metrics-bar__row">
        <span className="metrics-bar__label">CPU</span>
        <div className="metrics-bar__track">
          <div
            className="metrics-bar__fill"
            style={{
              width: `${Math.min(100, metrics.cpu_percent)}%`,
              backgroundColor: cpuColor,
            }}
          />
        </div>
        <span className="metrics-bar__value">{metrics.cpu_percent.toFixed(1)}%</span>
      </div>
      <div className="metrics-bar__row">
        <span className="metrics-bar__label">MEM</span>
        <div className="metrics-bar__track">
          <div
            className="metrics-bar__fill"
            style={{
              width: `${Math.min(100, metrics.memory_percent)}%`,
              backgroundColor: memColor,
            }}
          />
        </div>
        <span className="metrics-bar__value">
          {metrics.memory_usage_mb.toFixed(0)}MB
        </span>
      </div>
    </div>
  );
};
