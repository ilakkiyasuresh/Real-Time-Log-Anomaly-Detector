import { Activity, Gauge, AlertTriangle, BellRing, Brain, Layers, CheckCircle2 } from "lucide-react";

const STATUS_TEXT = { live: "Live", connecting: "Connecting…", reconnecting: "Reconnecting…" };

export default function StatusBar({ status, latest, alerts, linesPerSec }) {
  const open = alerts.filter((a) => a.status === "open");
  const count = (sev) => open.filter((a) => a.severity === sev).length;
  const ready = latest?.baseline_ready;
  const isAnomalous = latest?.anomalous;

  return (
    <div className="statusbar-container">
      <header className="header-row">
        <div className="brand-group">
          <div className="logo">
            <Activity size={24} />
          </div>
          <div className="brand-text">
            <h1>Log Anomaly Detector</h1>
            <span>Live anomaly detection</span>
          </div>
        </div>

        <div className="connection-pill">
          <span className={`dot ${status}`} aria-hidden="true" />
          <span>{STATUS_TEXT[status]}</span>
        </div>
      </header>

      <div className="kpi-grid">
        <div className="kpi-tile">
          <div className="kpi-icon-wrap"><Gauge size={24} /></div>
          <div className="kpi-content">
            <span className="kpi-label">Throughput</span>
            <span className="kpi-value">{linesPerSec.toFixed(0)}</span>
            <span className="kpi-sub">lines/s</span>
          </div>
        </div>

        <div className="kpi-tile">
          <div className="kpi-icon-wrap"><AlertTriangle size={24} /></div>
          <div className="kpi-content">
            <span className="kpi-label">Error rate now</span>
            <span className={`kpi-value ${isAnomalous ? 'critical' : ''}`}>
              {latest ? `${(latest.error_rate * 100).toFixed(1)}%` : "—"}
            </span>
            <span className="kpi-sub">
              {ready && latest.baseline_mean != null ? `normal ${(latest.baseline_mean * 100).toFixed(1)}%` : "calculating..."}
            </span>
          </div>
        </div>

        <div className="kpi-tile">
          <div className="kpi-icon-wrap"><BellRing size={24} /></div>
          <div className="kpi-content">
            <span className="kpi-label">Open alerts</span>
            <div className="kpi-badges">
              <span className="badge badge-critical">▲ {count("CRITICAL")}</span>
              <span className="badge badge-warning">◆ {count("WARNING")}</span>
              <span className="badge badge-info">● {count("INFO")}</span>
            </div>
          </div>
        </div>

        <div className="kpi-tile">
          <div className="kpi-icon-wrap"><Brain size={24} /></div>
          <div className="kpi-content">
            <span className="kpi-label">Baseline</span>
            {!latest ? (
              <span className="kpi-value">—</span>
            ) : ready ? (
              <span className="kpi-sub ready">
                <CheckCircle2 size={16} /> Ready
              </span>
            ) : (
              <span className="kpi-sub">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{marginRight: 4, verticalAlign: 'text-bottom'}}>
                  <path d="M21 12a9 9 0 1 1-6.219-8.56"></path>
                </svg>
                {latest.warmup_left} ticks left
              </span>
            )}
          </div>
        </div>

        <div className="kpi-tile">
          <div className="kpi-icon-wrap"><Layers size={24} /></div>
          <div className="kpi-content">
            <span className="kpi-label">Lines in window</span>
            <span className="kpi-value">{latest ? latest.total : "—"}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
