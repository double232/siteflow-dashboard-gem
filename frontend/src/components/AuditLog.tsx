import { useState } from 'react';
import dayjs from 'dayjs';

import { useAuditLogs } from '../api/hooks';
import type { AuditLogEntry } from '../api/types/audit';

const STATUS_COLORS: Record<string, string> = {
  success: '#22c55e',
  failure: '#ef4444',
  pending: '#f59e0b',
};

interface AuditLogProps {
  targetName?: string;
}

export const AuditLog = ({ targetName }: AuditLogProps) => {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useAuditLogs({ page, target_name: targetName });

  if (isLoading) {
    return <div className="panel audit-log">Loading audit logs...</div>;
  }

  if (!data?.logs.length) {
    return (
      <div className="panel audit-log">
        <div className="panel__title">Audit Log</div>
        <p className="audit-log__empty">No audit logs found</p>
      </div>
    );
  }

  return (
    <div className="panel audit-log">
      <div className="panel__title">
        Audit Log
        <span className="audit-log__count">({data.total} total)</span>
      </div>
      <div className="audit-log__list">
        {data.logs.map((log: AuditLogEntry) => (
          <div key={log.id} className="audit-log__item">
            <div className="audit-log__header">
              <span
                className="audit-log__status"
                style={{ color: STATUS_COLORS[log.status] || '#94a3b8' }}
              >
                {log.status.toUpperCase()}
              </span>
              <span className="audit-log__action">{log.action_type}</span>
              <span className="audit-log__time">
                {dayjs(log.timestamp).format('MMM D HH:mm:ss')}
              </span>
            </div>
            <div className="audit-log__target">
              {log.target_type}: {log.target_name}
            </div>
            {log.duration_ms && (
              <div className="audit-log__duration">{log.duration_ms.toFixed(0)}ms</div>
            )}
            {log.error_message && (
              <div className="audit-log__error">{log.error_message}</div>
            )}
          </div>
        ))}
      </div>
      {data.total_pages > 1 && (
        <div className="audit-log__pagination">
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
            Prev
          </button>
          <span>
            Page {page} of {data.total_pages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(data.total_pages, p + 1))}
            disabled={page === data.total_pages}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};
