export function LogPanel({ logs }: { logs: string[] }) {
  return (
    <section className="panel log-panel-full">
      <div className="panel-header">
        <div>
          <h2 className="panel-title">Activity Log</h2>
          <p className="panel-subtitle">Recent actions and system messages</p>
        </div>
      </div>
      <pre className="log-stream" role="log" aria-live="polite">
        {logs.join("\n")}
      </pre>
    </section>
  );
}