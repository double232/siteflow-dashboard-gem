interface CommandResult {
  title: string;
  output: string;
  isError: boolean;
  timestamp: Date;
}

interface Props {
  history: CommandResult[];
  onClear: () => void;
}

export const ConsoleOutput = ({ history, onClear }: Props) => {
  return (
    <div className="console-output">
      <div className="console-output__header">
        <span className="console-output__title">Console Output</span>
        {history.length > 0 && (
          <button className="console-output__clear" onClick={onClear}>
            Clear
          </button>
        )}
      </div>
      <div className="console-output__content">
        {history.length === 0 ? (
          <p className="console-output__placeholder">Command output will appear here</p>
        ) : (
          history.map((result, index) => (
            <div
              key={`${result.timestamp.getTime()}-${index}`}
              className={`console-output__entry ${result.isError ? 'console-output__entry--error' : 'console-output__entry--success'}`}
            >
              <div className="console-output__entry-header">
                <span className={`console-output__indicator ${result.isError ? 'console-output__indicator--error' : 'console-output__indicator--success'}`} />
                <strong>{result.title}</strong>
                <span className="console-output__time">
                  {result.timestamp.toLocaleTimeString()}
                </span>
              </div>
              <pre className="console-output__entry-output">{result.output}</pre>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
