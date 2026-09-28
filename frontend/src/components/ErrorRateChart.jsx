import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceArea
} from "recharts";

const fmtTime = (ts) =>
  new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="tooltip chart-tooltip">
      <div className="muted">{fmtTime(d.ts)}</div>
      <div style={{ marginTop: 4 }}>
        Error rate <strong style={{ color: "var(--cyan)" }}>{d.rate.toFixed(2)}%</strong>
      </div>
      {d.band && (
        <div className="muted">
          Normal range {d.band[0].toFixed(2)}–{d.band[1].toFixed(2)}%
        </div>
      )}
      <div className="muted">{d.total} lines in window</div>
      {d.anomaly != null && <div className="tooltip-flag">Anomaly detected</div>}
    </div>
  );
}

export default function ErrorRateChart({ metrics, injections }) {
  const data = metrics.map((m) => ({
    ts: m.ts,
    rate: m.error_rate * 100,
    total: m.total,
    band: m.baseline_ready ? [m.band[0] * 100, m.band[1] * 100] : null,
    anomaly: m.anomalous ? m.error_rate * 100 : null,
  }));

  if (!data.length) return <div className="empty">Waiting for the first tick…</div>;

  const baselineReady = metrics[metrics.length - 1]?.baseline_ready;
  
  // Prevent off-screen injections from stacking on the Y-axis
  const minTs = data[0]?.ts;
  const maxTs = data[data.length - 1]?.ts;
  const visibleInjections = injections?.filter(inj => 
    inj.startedAt <= maxTs && (inj.startedAt + inj.duration) >= minTs
  );

  return (
    <div className="chart-wrap" style={{ position: "relative" }}>
      {!baselineReady && (
        <div className="learning-chip">Learning what normal looks like…</div>
      )}
      <div className="legend" aria-hidden="true">
        <span className="key"><i className="key-line" /> Error rate</span>
        <span className="key"><i className="key-band" /> Learned normal range (mean ± 3σ)</span>
        <span className="key"><i className="key-dot" /> Anomalous tick</span>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--border)" strokeOpacity={0.5} vertical={false} />
          <XAxis
            dataKey="ts"
            tickFormatter={fmtTime}
            stroke="var(--border)"
            tick={{ fill: "var(--text-3)", fontSize: 11 }}
            minTickGap={48}
            domain={['dataMin', 'dataMax']}
            type="number"
          />
          <YAxis
            unit="%"
            width={48}
            stroke="var(--border)"
            tick={{ fill: "var(--text-3)", fontSize: 11 }}
            domain={[0, "auto"]}
            allowDecimals={false}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: "var(--border)" }} />
          
          {visibleInjections?.map((inj, i) => (
            <ReferenceArea
              key={i}
              x1={inj.startedAt}
              x2={inj.startedAt + inj.duration}
              fill="var(--brass)"
              fillOpacity={0.08}
              label={{ position: "insideTopLeft", value: inj.scenario, fill: "var(--brass-light)", fontSize: 11 }}
            />
          ))}

          <Area
            dataKey="band"
            stroke="none"
            fill="var(--band)"
            isAnimationActive={false}
            connectNulls={false}
          />
          <Line
            dataKey="rate"
            stroke="var(--cyan)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            dataKey="anomaly"
            stroke="none"
            dot={{ r: 4, fill: "var(--critical)", stroke: "var(--surface)", strokeWidth: 2 }}
            activeDot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
