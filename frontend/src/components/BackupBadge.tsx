import type { SiteBackupStatus, BackupStatus } from '../api/types/backups';

interface Props {
  backupStatus?: SiteBackupStatus;
}

const formatAge = (seconds: number | null): string => {
  if (seconds === null) return 'Never';

  const hours = Math.floor(seconds / 3600);
  const days = Math.floor(hours / 24);

  if (days > 0) {
    return `${days}d ago`;
  }
  if (hours > 0) {
    return `${hours}h ago`;
  }
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ago`;
};

const getStatusClass = (status: BackupStatus): string => {
  switch (status) {
    case 'ok':
      return 'backup-badge--ok';
    case 'warn':
      return 'backup-badge--warn';
    case 'fail':
      return 'backup-badge--fail';
    default:
      return '';
  }
};

const getStatusIcon = (status: BackupStatus): string => {
  switch (status) {
    case 'ok':
      return '[B]';
    case 'warn':
      return '[!]';
    case 'fail':
      return '[X]';
    default:
      return '[?]';
  }
};

export const BackupBadge = ({ backupStatus }: Props) => {
  if (!backupStatus) {
    return (
      <div className="backup-badge backup-badge--unknown" title="No backup data available">
        <span className="backup-badge__icon">[?]</span>
        <span className="backup-badge__label">Backups</span>
        <span className="backup-badge__value">No data</span>
      </div>
    );
  }

  const { overall_status, rpo_seconds_db, rpo_seconds_uploads } = backupStatus;
  const dbAge = formatAge(rpo_seconds_db);
  const uploadsAge = formatAge(rpo_seconds_uploads);

  return (
    <div
      className={`backup-badge ${getStatusClass(overall_status)}`}
      title={`DB: ${dbAge}, Uploads: ${uploadsAge}`}
    >
      <span className="backup-badge__icon">{getStatusIcon(overall_status)}</span>
      <span className="backup-badge__label">Backups</span>
      <span className="backup-badge__ages">
        <span className="backup-badge__age">DB: {dbAge}</span>
        <span className="backup-badge__age">Up: {uploadsAge}</span>
      </span>
    </div>
  );
};
