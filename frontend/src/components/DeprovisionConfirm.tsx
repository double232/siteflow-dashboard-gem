import { useState } from 'react';

import { useDeprovisionSite } from '../api/hooks';

interface DeprovisionConfirmProps {
  siteName: string;
  onSuccess?: () => void;
  onCancel?: () => void;
}

export const DeprovisionConfirm = ({
  siteName,
  onSuccess,
  onCancel,
}: DeprovisionConfirmProps) => {
  const { mutateAsync: deprovisionSite, isPending } = useDeprovisionSite();

  const [removeVolumes, setRemoveVolumes] = useState(false);
  const [removeFiles, setRemoveFiles] = useState(false);
  const [confirmName, setConfirmName] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (confirmName !== siteName) {
      setError('Site name does not match');
      return;
    }

    try {
      await deprovisionSite({
        name: siteName,
        remove_volumes: removeVolumes,
        remove_files: removeFiles,
      });
      onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to deprovision site');
    }
  };

  return (
    <div className="panel deprovision-confirm">
      <div className="panel__title">Deprovision Site</div>
      <div className="deprovision-warning">
        You are about to deprovision <strong>{siteName}</strong>. This action will stop
        and remove all containers.
      </div>

      <form onSubmit={handleSubmit}>
        <div className="form-group checkbox">
          <label>
            <input
              type="checkbox"
              checked={removeVolumes}
              onChange={(e) => setRemoveVolumes(e.target.checked)}
            />
            Remove Docker volumes (database data)
          </label>
        </div>

        <div className="form-group checkbox">
          <label>
            <input
              type="checkbox"
              checked={removeFiles}
              onChange={(e) => setRemoveFiles(e.target.checked)}
            />
            Remove site files
          </label>
        </div>

        <div className="form-group">
          <label htmlFor="confirm-name">Type "{siteName}" to confirm</label>
          <input
            id="confirm-name"
            type="text"
            value={confirmName}
            onChange={(e) => setConfirmName(e.target.value)}
            placeholder={siteName}
          />
        </div>

        {error && <div className="form-error">{error}</div>}

        <div className="form-actions">
          <button type="button" onClick={onCancel} disabled={isPending}>
            Cancel
          </button>
          <button
            type="submit"
            className="danger"
            disabled={isPending || confirmName !== siteName}
          >
            {isPending ? 'Deprovisioning...' : 'Deprovision'}
          </button>
        </div>
      </form>
    </div>
  );
};
