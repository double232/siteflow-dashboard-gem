import { useEffect, useRef } from 'react';

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

const FOCUSABLE_SELECTORS = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

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
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    if (typeof document === 'undefined') {
      return;
    }

    const container = panelRef.current;
    if (!container) {
      return;
    }

    const previouslyFocused = document.activeElement as HTMLElement | null;
    const getFocusable = () =>
      Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTORS)).filter(
        (element) => !element.hasAttribute('disabled') && element.tabIndex !== -1
      );

    const focusables = getFocusable();
    (focusables[0] ?? container).focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key === 'Tab') {
        const tabbables = getFocusable();
        if (!tabbables.length) {
          event.preventDefault();
          return;
        }
        const first = tabbables[0];
        const last = tabbables[tabbables.length - 1];
        const active = document.activeElement as HTMLElement;
        if (event.shiftKey && active === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && active === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };

    container.addEventListener('keydown', handleKeyDown);

    return () => {
      container.removeEventListener('keydown', handleKeyDown);
      previouslyFocused?.focus();
    };
  }, [isOpen, onClose]);

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
        ref={panelRef}
        className={`mobile-settings ${isOpen ? 'mobile-settings--visible' : ''}`}
        role="dialog"
        aria-label="Settings"
        aria-modal="true"
        aria-hidden={!isOpen}
        tabIndex={-1}
      >
        <div className="mobile-settings__handle">
          <div className="mobile-settings__handle-bar" />
        </div>
        <h2 className="mobile-settings__title">Settings</h2>
        <div className="mobile-settings__actions">
          <button
            className="mobile-settings__btn"
            type="button"
            onClick={() => handleAction(onShowProvision)}
          >
            + New Site
          </button>
          <button
            className="mobile-settings__btn"
            type="button"
            onClick={() => handleAction(onShowAudit)}
          >
            View Audit Log
          </button>
          <button
            className="mobile-settings__btn"
            type="button"
            onClick={() => handleAction(onRefresh)}
            disabled={isRefreshing}
          >
            {isRefreshing ? 'Refreshing...' : 'Refresh Sites'}
          </button>
          <button
            className="mobile-settings__btn"
            type="button"
            onClick={() => handleAction(onReloadCaddy)}
            disabled={isReloadingCaddy}
          >
            {isReloadingCaddy ? 'Reloading...' : 'Reload Caddy'}
          </button>
          <button
            className="mobile-settings__btn theme-toggle"
            type="button"
            onClick={onToggleTheme}
          >
            Theme: {theme === 'light' ? 'Light' : 'Dark'}
          </button>
        </div>
      </div>
    </>
  );
};
