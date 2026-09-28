# Backend contract

WebSocket: connect to ws(s)://<current host>/ws (relative, through the Vite proxy). 
Server sends JSON messages {type, ...}:
- {type:"snapshot", data:{logs: LogLine[] (oldest first, up to 200), metrics: Metric[] (oldest first, up to 360), alerts: Alert[] (newest first, up to 50)}} — sent once right after connecting.
- {type:"log_batch", data: LogLine[]} — every 250 ms when there are new lines (oldest first in the batch).
- {type:"metric", data: Metric} — once per tick (default every 5 s; 2 s in fast dev mode).
- {type:"alert", event: "new"|"escalated"|"updated"|"resolved"|"acked"|"false_positive", data: Alert}
- {type:"alert_pushed", data:{id: string, cloudwatch: boolean, sns: boolean}} — AWS delivery result for an alert.

LogLine = {ts: number (unix seconds, float), level: "INFO"|"WARN"|"ERROR", service: string, msg: string, template_id: number|null}

Metric = {ts: number, error_rate: number (0-.1), total: number (lines in window), errors: number, baseline_mean: number|null (0-.1), band: [low, high] (0-.1), baseline_ready: boolean, warmup_left: number (ticks), per_service: {[service]: {error_rate: number, total: number}}, anomalous: boolean}

Alert = {id: string, fingerprint: string ("detector:metric:service"), severity: "INFO"|"WARNING"|"CRITICAL", status: "open"|"resolved"|"acked"|"false_positive", title: string, reason: string, service: string ("*" means all services), first_seen: number, last_seen: number, count: number, evidence: string[] (raw log lines), score: number, pushed: {cloudwatch: boolean, sns: boolean}}

The detector name is the first part of fingerprint: "error_rate" | "volume" | "new_template" | "silence" | "isolation_forest".

Severity only goes up while an alert is open. An alert with the same id arrives many times (new, escalated, updated, resolved...): always upsert by id, and never lose a pushed flag that was already true (OR the flags).

REST (relative URLs):
- GET /api/health -> {ok, lines_total, clients, aws: "on"|"mock"}
- GET /api/alerts?limit=50 -> Alert[] newest first
- POST /api/alerts/{id}/ack -> Alert
- POST /api/alerts/{id}/false-positive -> Alert (mutes that fingerprint for 10 minutes)
- POST /api/inject?scenario=<name>&service=<name>&duration=<seconds> -> {injected: {scenario, service, elapsed_s, duration_s}}
- GET /api/generator/status -> {file, base_rate_per_s, current_rate_per_s, lines_written, uptime_s, active:[{scenario, service, elapsed_s, duration_s}]}   (added in Phase 8)
- POST /api/generator/reset -> {ok:true}   (added in Phase 8)

Scenarios: error_burst, error_creep, new_exception, silence, traffic_spike, latency. 
Services: auth, gateway, orders, payments.
