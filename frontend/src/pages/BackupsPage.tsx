import { useState } from 'react';

import {
  useBackupSummary,
  useBackupSite,
  useBackupAllSites,
  useBackupSystem,
  useRestoreSite,
  useRestoreSystem,
  useSnapshots,
  useSystemBackupStatus,
} from '../api/hooks';
import type { BackupStatus, SnapshotInfo } from '../api/types/backups';

interface CommandResult {
  title: string;
  output: string;
  isError: boolean;
  timestamp: Date;
}

const formatTimeAgo = (seconds: number | null | undefined): string => {
  if (seconds === null || seconds === undefined) return 'Never';
  if (seconds < 60) return 'Just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
};

const StatusBadge = ({ status }: { status: BackupStatus }) => {
  const colors = {
    ok: 'status-badge--ok',
    warn: 'status-badge--warn',
    fail: 'status-badge--fail',
  };
  return (
    <span className={`status-badge ${colors[status]}`}>
      {status.toUpperCase()}
    </span>
  );
};

interface SnapshotPickerProps {
  snapshots: SnapshotInfo[];
  onSelect: (snapshot: SnapshotInfo) => void;
  onCancel: () => void;
  title: string;
}

const SnapshotPicker = ({ snapshots, onSelect, onCancel, title }: SnapshotPickerProps) => (
  <div className="snapshot-picker-overlay">
    <div className="snapshot-picker">
      <h3>{title}</h3>
      <div className="snapshot-list">
        {snapshots.length === 0 ? (
          <p className="snapshot-empty">No snapshots available</p>
        ) : (
          snapshots.map((snap) => (
            <div key={snap.id} className="snapshot-item" onClick={() => onSelect(snap)}>
              <div className="snapshot-item__id">{snap.short_id}</div>
              <div className="snapshot-item__time">
                {new Date(snap.time).toLocaleString()}
              </div>
              <div className="snapshot-item__tags">
                {snap.tags.map((tag) => (
                  <span key={tag} className="snapshot-tag">{tag}</span>
                ))}
              </div>
              <div className="snapshot-item__paths">
                {snap.paths.join(', ')}
              </div>
            </div>
          ))
        )}
      </div>
      <button className="snapshot-picker__cancel" onClick={onCancel}>Cancel</button>
    </div>
  </div>
);

export const BackupsPage = () => {
  const { data: backupSummary, refetch: refetchSummary } = useBackupSummary();
  const { data: systemStatus, refetch: refetchSystemStatus } = useSystemBackupStatus();
  const { data: snapshotsData, refetch: refetchSnapshots } = useSnapshots();

  const backupSite = useBackupSite();
  const backupAllSites = useBackupAllSites();
  const backupSystem = useBackupSystem();
  const restoreSite = useRestoreSite();
  const restoreSystem = useRestoreSystem();

  const [commandHistory, setCommandHistory] = useState<CommandResult[]>([]);
  const [restoreTarget, setRestoreTarget] = useState<{ type: 'site' | 'system'; site?: string } | null>(null);

  const addToHistory = (result: CommandResult) => {
    setCommandHistory((prev) => [result, ...prev]);
  };

  const handleBackupSite = async (site: string) => {
    addToHistory({
      title: `Backup: ${site}`,
      output: 'Starting backup...',
      isError: false,
      timestamp: new Date(),
    });

    try {
      const result = await backupSite.mutateAsync(site);
      addToHistory({
        title: `Backup: ${site}`,
        output: result.output,
        isError: result.status === 'error',
        timestamp: new Date(),
      });
      refetchSummary();
      refetchSnapshots();
    } catch (e) {
      addToHistory({
        title: `Backup: ${site}`,
        output: e instanceof Error ? e.message : 'Backup failed',
        isError: true,
        timestamp: new Date(),
      });
    }
  };

  const handleBackupAllSites = async () => {
    addToHistory({
      title: 'Backup: All Sites',
      output: 'Starting backup of all sites...',
      isError: false,
      timestamp: new Date(),
    });

    try {
      const result = await backupAllSites.mutateAsync();
      addToHistory({
        title: 'Backup: All Sites',
        output: result.output,
        isError: result.status === 'error',
        timestamp: new Date(),
      });
      refetchSummary();
      refetchSnapshots();
    } catch (e) {
      addToHistory({
        title: 'Backup: All Sites',
        output: e instanceof Error ? e.message : 'Backup failed',
        isError: true,
        timestamp: new Date(),
      });
    }
  };

  const handleBackupSystem = async () => {
    addToHistory({
      title: 'Backup: System',
      output: 'Starting full system backup... This may take a while.',
      isError: false,
      timestamp: new Date(),
    });

    try {
      const result = await backupSystem.mutateAsync();
      addToHistory({
        title: 'Backup: System',
        output: result.output,
        isError: result.status === 'error',
        timestamp: new Date(),
      });
      refetchSystemStatus();
      refetchSnapshots();
    } catch (e) {
      addToHistory({
        title: 'Backup: System',
        output: e instanceof Error ? e.message : 'Backup failed',
        isError: true,
        timestamp: new Date(),
      });
    }
  };

  const handleRestoreSelect = (snapshot: SnapshotInfo) => {
    if (!restoreTarget) return;

    const confirmMsg = restoreTarget.type === 'system'
      ? `RESTORE ENTIRE SYSTEM from snapshot ${snapshot.short_id}? This will overwrite all files in /opt.`
      : `Restore site ${restoreTarget.site} from snapshot ${snapshot.short_id}?`;

    if (!confirm(confirmMsg)) {
      setRestoreTarget(null);
      return;
    }

    if (restoreTarget.type === 'system') {
      handleRestoreSystem(snapshot.id);
    } else if (restoreTarget.site) {
      handleRestoreSite(restoreTarget.site, snapshot.id);
    }
    setRestoreTarget(null);
  };

  const handleRestoreSite = async (site: string, snapshotId: string) => {
    addToHistory({
      title: `Restore: ${site}`,
      output: `Restoring from snapshot ${snapshotId}...`,
      isError: false,
      timestamp: new Date(),
    });

    try {
      const result = await restoreSite.mutateAsync({ site, snapshotId });
      addToHistory({
        title: `Restore: ${site}`,
        output: result.output,
        isError: result.status === 'error',
        timestamp: new Date(),
      });
    } catch (e) {
      addToHistory({
        title: `Restore: ${site}`,
        output: e instanceof Error ? e.message : 'Restore failed',
        isError: true,
        timestamp: new Date(),
      });
    }
  };

  const handleRestoreSystem = async (snapshotId: string) => {
    addToHistory({
      title: 'Restore: System',
      output: `Starting SYSTEM RESTORE from ${snapshotId}...`,
      isError: false,
      timestamp: new Date(),
    });

    try {
      const result = await restoreSystem.mutateAsync(snapshotId);
      addToHistory({
        title: 'Restore: System',
        output: result.output,
        isError: result.status === 'error',
        timestamp: new Date(),
      });
    } catch (e) {
      addToHistory({
        title: 'Restore: System',
        output: e instanceof Error ? e.message : 'Restore failed',
        isError: true,
        timestamp: new Date(),
      });
    }
  };

  const isAnyPending = backupSite.isPending || backupAllSites.isPending ||
    backupSystem.isPending || restoreSite.isPending || restoreSystem.isPending;

  return (
    <div className="backups-page">
      {/* System Backup Section */}
      <section className="backup-section backup-section--system">
        <div className="backup-section__header">
          <h2>System Backup</h2>
          {systemStatus && (
            <div className="backup-section__status">
              <StatusBadge status={systemStatus.overall_status} />
              <span className="backup-section__time">
                Last backup: {formatTimeAgo(systemStatus.rpo_seconds_system)}
              </span>
            </div>
          )}
        </div>
        <p className="backup-section__desc">
          Full system backup includes all sites, gateway config, and data directories.
        </p>
        <div className="backup-section__actions">
          <button
            className="btn btn--primary"
            onClick={handleBackupSystem}
            disabled={isAnyPending}
          >
            {backupSystem.isPending ? 'Backing up...' : 'Backup System'}
          </button>
          <button
            className="btn btn--danger"
            onClick={() => setRestoreTarget({ type: 'system' })}
            disabled={isAnyPending}
          >
            Restore System
          </button>
        </div>
      </section>

      {/* All Sites Section */}
      <section className="backup-section backup-section--all-sites">
        <div className="backup-section__header">
          <h2>All Sites</h2>
        </div>
        <p className="backup-section__desc">
          Backup all sites sequentially. This may take several minutes.
        </p>
        <div className="backup-section__actions">
          <button
            className="btn btn--primary"
            onClick={handleBackupAllSites}
            disabled={isAnyPending}
          >
            {backupAllSites.isPending ? 'Backing up...' : 'Backup All Sites'}
          </button>
        </div>
      </section>

      {/* Per-Site Table */}
      <section className="backup-section backup-section--sites">
        <h2>Site Backups</h2>
        <table className="backup-table">
          <thead>
            <tr>
              <th>Site</th>
              <th>Last Backup</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {backupSummary?.sites.map((site) => (
              <tr key={site.site}>
                <td className="backup-table__site">{site.site}</td>
                <td className="backup-table__time">
                  {formatTimeAgo(site.rpo_seconds_db || site.rpo_seconds_uploads)}
                </td>
                <td className="backup-table__status">
                  <StatusBadge status={site.overall_status} />
                </td>
                <td className="backup-table__actions">
                  <button
                    className="btn btn--small btn--primary"
                    onClick={() => handleBackupSite(site.site)}
                    disabled={isAnyPending}
                  >
                    {backupSite.isPending ? '...' : 'Backup'}
                  </button>
                  <button
                    className="btn btn--small btn--secondary"
                    onClick={() => setRestoreTarget({ type: 'site', site: site.site })}
                    disabled={isAnyPending}
                  >
                    Restore
                  </button>
                </td>
              </tr>
            ))}
            {(!backupSummary || backupSummary.sites.length === 0) && (
              <tr>
                <td colSpan={4} className="backup-table__empty">
                  No sites with backup history
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      {/* Console Output */}
      <aside className="backup-console">
        <div className="console-output">
          <div className="console-output__header">
            <span className="console-output__title">Console Output</span>
            {commandHistory.length > 0 && (
              <button className="console-output__clear" onClick={() => setCommandHistory([])}>
                Clear
              </button>
            )}
          </div>
          <div className="console-output__content">
            {commandHistory.length === 0 ? (
              <p className="console-output__placeholder">Backup output will appear here</p>
            ) : (
              commandHistory.map((result, index) => (
                <div
                  key={`${result.timestamp.getTime()}-${index}`}
                  className={`console-output__entry ${result.isError ? 'console-output__entry--error' : 'console-output__entry--success'}`}
                >
                  <div className="console-output__entry-header">
                    <span className="console-output__entry-title">{result.title}</span>
                    <span className="console-output__entry-time">
                      {result.timestamp.toLocaleTimeString()}
                    </span>
                  </div>
                  <pre className="console-output__entry-output">{result.output}</pre>
                </div>
              ))
            )}
          </div>
        </div>
      </aside>

      {/* Snapshot Picker Modal */}
      {restoreTarget && snapshotsData && (
        <SnapshotPicker
          snapshots={restoreTarget.type === 'system'
            ? snapshotsData.snapshots.filter((s) => s.tags.includes('type:system'))
            : snapshotsData.snapshots.filter((s) => s.tags.includes(`site:${restoreTarget.site}`))
          }
          onSelect={handleRestoreSelect}
          onCancel={() => setRestoreTarget(null)}
          title={restoreTarget.type === 'system'
            ? 'Select System Snapshot to Restore'
            : `Select Snapshot for ${restoreTarget.site}`
          }
        />
      )}
    </div>
  );
};
