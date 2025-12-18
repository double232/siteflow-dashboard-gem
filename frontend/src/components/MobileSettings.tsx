interface Props {
  isOpen: boolean;
  onClose: () => void;
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
  onShowProvision: () => void;
  onShowAudit: () => void;
  onRefresh: () => void;
  onReloadCaddy: () => void;
  isRefreshing?: boolean;
  isReloadingCaddy?: boolean;
}

export const MobileSettings = ({
  isOpen,
  onClose,
  theme,
  onToggleTheme,
  onShowProvision,
  onShowAudit,
  onRefresh,
  onReloadCaddy,
  isRefreshing = false,
  isReloadingCaddy = false,
}: Props) => {
  const handleAction = (action: () => void) => {
    action();
    onClose();
  };

  return (
    <>
      <div
        className={`mobile-settings-overlay ${isOpen ? 'mobile-settings-overlay--visible' : ''}`}
        onClick={onClose}
        aria-hidden={!isOpen}
      />
      <div
        className={`mobile-settings ${isOpen ? 'mobile-settings--visible' : ''}`}
        role="dialog"
        aria-label="Settings"
        aria-hidden={!isOpen}
      >
        <div className="mobile-settings__handle">
          <div className="mobile-settings__handle-bar" />
        </div>
        <h2 className="mobile-settings__title">Settings</h2>
        <div className="mobile-settings__actions">
          <button
            className="mobile-settings__btn"
            onClick={() => handleAction(onShowProvision)}
          >
            + New Site
          </button>
          <button
            className="mobile-settings__btn"
            onClick={() => handleAction(onShowAudit)}
          >
            View Audit Log
          </button>
          <button
            className="mobile-settings__btn"
            onClick={() => handleAction(onRefresh)}
            disabled={isRefreshing}
          >
            {isRefreshing ? 'Refreshing...' : 'Refresh Sites'}
          </button>
          <button
            className="mobile-settings__btn"
            onClick={() => handleAction(onReloadCaddy)}
            disabled={isReloadingCaddy}
          >
            {isReloadingCaddy ? 'Reloading...' : 'Reload Caddy'}
          </button>
          <button
            className="mobile-settings__btn theme-toggle"
            onClick={onToggleTheme}
          >
            Theme: {theme === 'light' ? 'Light' : 'Dark'}
          </button>
        </div>
      </div>
    </>
  );
};
