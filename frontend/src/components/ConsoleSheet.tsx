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

export const ConsoleSheet = ({ isOpen, onClose, history, onClear }: Props) => {
  return (
    <>
      <div
        className={`console-sheet-overlay ${isOpen ? 'console-sheet-overlay--visible' : ''}`}
        onClick={onClose}
        aria-hidden={!isOpen}
      />
      <div
        className={`console-sheet ${isOpen ? 'console-sheet--visible' : ''}`}
        role="dialog"
        aria-label="Console Output"
        aria-hidden={!isOpen}
      >
        <div className="console-sheet__handle">
          <div className="console-sheet__handle-bar" />
        </div>
        <div className="console-sheet__header">
          <span className="console-sheet__title">Console Output</span>
          <div className="console-sheet__actions">
            {history.length > 0 && (
              <button className="console-sheet__close" onClick={onClear}>
                Clear
              </button>
            )}
            <button className="console-sheet__close" onClick={onClose}>
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
