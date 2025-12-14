import { useState } from 'react';
import type { ContainerStatus } from '../api/types';

interface Props {
  siteName: string;
  containers: ContainerStatus[];
  onFetchLogs: (container: string) => Promise<string>;
  onClose: () => void;
}

export const LogModal = ({ siteName, containers, onFetchLogs, onClose }: Props) => {
  const [selectedContainer, setSelectedContainer] = useState<string>(
    containers[0]?.name || ''
  );
  const [logs, setLogs] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFetchLogs = async () => {
    if (!selectedContainer) return;

    setLoading(true);
    setError(null);
    try {
      const result = await onFetchLogs(selectedContainer);
      setLogs(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch logs');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal--wide log-modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal__close" onClick={onClose}>
          X
        </button>
        <h3>Logs: {siteName}</h3>

        <div className="log-modal__controls">
          <label htmlFor="container-select">Container:</label>
          <select
            id="container-select"
            value={selectedContainer}
            onChange={(e) => setSelectedContainer(e.target.value)}
          >
            {containers.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name} ({c.status})
              </option>
            ))}
          </select>
          <button onClick={handleFetchLogs} disabled={loading || !selectedContainer}>
            {loading ? 'Loading...' : 'Fetch Logs'}
          </button>
        </div>

        {error && <div className="log-modal__error">{error}</div>}

        <div className="log-modal__output">
          {logs ? (
            <pre>{logs}</pre>
          ) : (
            <p className="log-modal__placeholder">
              Select a container and click "Fetch Logs" to view logs
            </p>
          )}
        </div>
      </div>
    </div>
  );
};
