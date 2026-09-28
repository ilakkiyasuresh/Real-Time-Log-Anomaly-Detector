import { useState, useEffect } from "react";
import { Cloud, Mail, CheckCircle2 } from "lucide-react";

const ICON = { CRITICAL: "▲", WARNING: "◆", INFO: "●" };

export function SeverityPill({ severity, count }) {
  return (
    <span className={`pill pill-${severity.toLowerCase()}`}>
      <span aria-hidden="true">{ICON[severity]}</span> {severity}
      {count != null && <strong> {count}</strong>}
    </span>
  );
}

const fmt = (ts) =>
  new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

async function post(path) {
  await fetch(path, { method: "POST" });
}

function LiveCounter({ startedAt }) {
  const [now, setNow] = useState(Date.now() / 1000);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(timer);
  }, []);
  return <span>open for {Math.floor(now - startedAt)}s</span>;
}

function DeliveryIcon({ ok, Icon, label }) {
  return (
    <span className="delivery-icon" title={label}>
      <Icon size={14} className={ok ? "delivered" : "pending"} />
      {ok && <CheckCircle2 size={10} className="check-badge" />}
    </span>
  );
}

function formatEvidence(lines) {
  return lines.map((line, i) => {
    if (line.includes("ERROR")) return <div key={i} className="ev-error">{line}</div>;
    if (line.includes("WARN")) return <div key={i} className="ev-warn">{line}</div>;
    return <div key={i}>{line}</div>;
  });
}

export default function AlertFeed({ alerts }) {
  const [filters, setFilters] = useState({ CRITICAL: true, WARNING: true, INFO: true, hideResolved: false });

  const toggleFilter = (k) => setFilters((f) => ({ ...f, [k]: !f[k] }));

  const filtered = alerts.filter(a => {
    if (filters.hideResolved && a.status === "resolved") return false;
    return filters[a.severity];
  });

  return (
    <div className="alert-feed-wrapper">
      <div className="alert-filters">
        <div className="filter-chips">
          {["CRITICAL", "WARNING", "INFO"].map(sev => (
            <button key={sev} className={`filter-chip ${filters[sev] ? 'active' : ''}`} onClick={() => toggleFilter(sev)}>
              {ICON[sev]} {sev}
            </button>
          ))}
        </div>
        <label className="toggle-label">
          <input type="checkbox" checked={filters.hideResolved} onChange={() => toggleFilter("hideResolved")} />
          Hide resolved
        </label>
      </div>

      {!filtered.length ? (
        <div className="empty-state">
          <CheckCircle2 size={32} className="empty-icon" />
          <div className="empty-title">All systems normal</div>
          <div className="empty-hint">Inject an anomaly to test</div>
        </div>
      ) : (
        <ul className="alerts">
          {filtered.map((a) => (
            <li key={a.id} className={`alert-card alert-${a.severity.toLowerCase()} status-${a.status}`}>
              <div className="alert-top">
                <SeverityPill severity={a.severity} />
                <div className="alert-svc">
                  <span className={`svc-dot svc-${a.service === '*' ? 'unknown' : a.service}`} />
                  {a.service}
                </div>
                <span className="muted" style={{marginLeft: "auto"}}>{fmt(a.first_seen)}</span>
              </div>
              <div className="alert-title">{a.title}</div>
              <div className="alert-reason">{a.reason}</div>
              
              <div className="alert-meta">
                <span>seen {a.count}×</span>
                <span>•</span>
                {a.status === "open" ? <LiveCounter startedAt={a.first_seen} /> : "resolved"}
                
                <div className="delivery-status">
                  <DeliveryIcon ok={a.pushed?.cloudwatch} Icon={Cloud} label="CloudWatch" />
                  {a.severity === "CRITICAL" && <DeliveryIcon ok={a.pushed?.sns} Icon={Mail} label="SNS" />}
                </div>
              </div>

              {a.evidence?.length > 0 && (
                <details className="evidence-details">
                  <summary>Evidence ({a.evidence.length} lines)</summary>
                  <pre className="evidence-block">{formatEvidence(a.evidence)}</pre>
                </details>
              )}

              {a.status === "open" && (
                <div className="alert-actions">
                  <button className="primary" onClick={() => post(`/api/alerts/${a.id}/ack`)}>Acknowledge</button>
                  <button className="secondary" onClick={() => post(`/api/alerts/${a.id}/false-positive`)}>
                    False positive
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
