import classNames from 'classnames';

const STATUS_COLORS: Record<string, string> = {
  running: '#22c55e',
  stopped: '#f97316',
  degraded: '#facc15',
  unknown: '#94a3b8',
};

interface Props {
  status: string;
}

export const StatusBadge = ({ status }: Props) => {
  const normalized = status?.toLowerCase() || 'unknown';
  const color = STATUS_COLORS[normalized] || STATUS_COLORS.unknown;
  return (
    <span
      className={classNames('status-badge')}
      style={{ backgroundColor: `${color}22`, color }}
    >
      {normalized}
    </span>
  );
};
