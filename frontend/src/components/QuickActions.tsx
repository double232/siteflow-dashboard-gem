interface Props {
  siteName: string;
  onSiteAction: (action: 'start' | 'stop' | 'restart') => void;
  onViewLogs: () => void;
  onDeprovision: () => void;
  onDeploy: () => void;
  onPull: () => void;
  disabled?: boolean;
}

export const QuickActions = ({
  siteName,
  onSiteAction,
  onViewLogs,
  onDeprovision,
  onDeploy,
  onPull,
  disabled = false,
}: Props) => {
  return (
    <div className="quick-actions">
      <div className="quick-actions__row">
        <button
          type="button"
          className="action-start"
          disabled={disabled}
          onClick={() => onSiteAction('start')}
          title={`Start all containers in ${siteName}`}
        >
          Start
        </button>
        <button
          type="button"
          className="action-stop"
          disabled={disabled}
          onClick={() => onSiteAction('stop')}
          title={`Stop all containers in ${siteName}`}
        >
          Stop
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onSiteAction('restart')}
          title={`Restart all containers in ${siteName}`}
        >
          Restart
        </button>
      </div>
      <div className="quick-actions__row">
        <button
          type="button"
          className="action-deploy"
          disabled={disabled}
          onClick={onDeploy}
          title="Deploy from GitHub"
        >
          Deploy
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={onPull}
          title="Pull latest changes"
        >
          Pull
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={onViewLogs}
          title="View container logs"
        >
          Logs
        </button>
      </div>
      <div className="quick-actions__row">
        <button
          type="button"
          className="action-danger"
          disabled={disabled}
          onClick={onDeprovision}
          title={`Remove ${siteName}`}
        >
          Deprovision
        </button>
      </div>
    </div>
  );
};
