import { useEffect, useRef } from 'react';

interface CommandResult {
  title: string;
  output: string;
  isError: boolean;
  timestamp: Date;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  history: CommandResult[];
  onClear: () => void;
}

const FOCUSABLE_SELECTORS = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

export const ConsoleSheet = ({ isOpen, onClose, history, onClear }: Props) => {
  const sheetRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    if (typeof document === 'undefined') {
      return;
    }

    const container = sheetRef.current;
    if (!container) {
      return;
    }

    const previouslyFocused = document.activeElement as HTMLElement | null;
    const getFocusable = () =>
      Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTORS)).filter(
        (element) => !element.hasAttribute('disabled') && element.tabIndex !== -1
      );

    const initial = getFocusable();
    (initial[0] ?? container).focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key === 'Tab') {
        const focusableItems = getFocusable();
        if (!focusableItems.length) {
          event.preventDefault();
          return;
        }
        const first = focusableItems[0];
        const last = focusableItems[focusableItems.length - 1];
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
  }, [isOpen, onClose, history.length]);

  return (
    <>
      <div
        className={`console-sheet-overlay ${isOpen ? 'console-sheet-overlay--visible' : ''}`}
        onClick={onClose}
        aria-hidden={!isOpen}
      />
      <div
        ref={sheetRef}
        className={`console-sheet ${isOpen ? 'console-sheet--visible' : ''}`}
        role="dialog"
        aria-label="Console Output"
        aria-modal="true"
        aria-hidden={!isOpen}
        tabIndex={-1}
      >
        <div className="console-sheet__handle">
          <div className="console-sheet__handle-bar" />
        </div>
        <div className="console-sheet__header">
          <span className="console-sheet__title">Console Output</span>
          <div className="console-sheet__actions">
            {history.length > 0 && (
              <button className="console-sheet__close" type="button" onClick={onClear}>
                Clear
              </button>
            )}
            <button className="console-sheet__close" type="button" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
        <div className="console-sheet__content">
          {history.length === 0 ? (
            <p className="console-output__placeholder">Command output will appear here</p>
          ) : (
            history.map((result, index) => (
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
    </>
  );
};
