import { useState } from "react";
import { useLiveFeed } from "./hooks/useLiveFeed.js";
import StatusBar from "./components/StatusBar.jsx";
import ErrorRateChart from "./components/ErrorRateChart.jsx";
import LogTail from "./components/LogTail.jsx";
import AlertFeed from "./components/AlertFeed.jsx";
import ChaosLab from "./components/ChaosLab.jsx";

export default function App() {
  const { status, logs, metrics, alerts, linesPerSec } = useLiveFeed();
  const latest = metrics[metrics.length - 1];
  const [injections, setInjections] = useState([]);
  const [timeRange, setTimeRange] = useState("5m");

  const filterMetrics = (metrics, range) => {
    if (!metrics.length) return [];
    if (range === "all") return metrics;
    const cutoff = Date.now() / 1000 - (range === "2m" ? 120 : 300);
    return metrics.filter((m) => m.ts >= cutoff);
  };
  
  const filteredMetrics = filterMetrics(metrics, timeRange);

  return (
    <div className="app">
      <StatusBar status={status} latest={latest} alerts={alerts} linesPerSec={linesPerSec} />
      <main className="grid">
        <section className="panel chart-panel">
          <div className="panel-head">
            <h2>Error rate vs learned baseline</h2>
            <div className="segmented-control">
              <button className={timeRange === "2m" ? "active" : ""} onClick={() => setTimeRange("2m")}>Last 2 min</button>
              <button className={timeRange === "5m" ? "active" : ""} onClick={() => setTimeRange("5m")}>5 min</button>
              <button className={timeRange === "all" ? "active" : ""} onClick={() => setTimeRange("all")}>All</button>
            </div>
          </div>
          <ErrorRateChart metrics={filteredMetrics} injections={injections} />
          
          <ChaosLab onInject={(inj) => setInjections((prev) => [...prev, inj])} injections={injections} alerts={alerts} />
        </section>
        <section className="panel logs-panel">
          <div className="panel-head">
            <h2>Live log stream</h2>
            <span className="muted">newest first</span>
          </div>
          <LogTail logs={logs} />
        </section>
        <section className="panel alerts-panel">
          <div className="panel-head">
            <h2>Alerts</h2>
            <span className="muted">{alerts.length} total</span>
          </div>
          <AlertFeed alerts={alerts} />
        </section>
      </main>
    </div>
  );
}
