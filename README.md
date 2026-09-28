# Real-Time Log Anomaly Detector

Learns what "normal" looks like from a live log stream (no static blacklist), detects deviations,
scores severity (INFO / WARNING / CRITICAL), streams everything to a React dashboard over WebSockets,
and pushes alerts to AWS CloudWatch Logs and SNS.

## Run it (3 terminals)

```bash
# 1. Log generator (writes generator/logs/app.log, control API on :8099)
cd generator && python log_generator.py --rate 20

# 2. Backend (FastAPI on :8000)
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env                                # AWS_ENABLED=0 = mock mode
uvicorn app.main:app --port 8000
# faster warm-up for development:
# WINDOW_S=20 TICK_S=2 WARMUP_TICKS=10 uvicorn app.main:app --port 8000

# 3. Dashboard (Vite on :5173, proxies /api and /ws to :8000)
cd frontend && npm install && npm run dev
```

Open http://localhost:5173, wait for "Baseline: Ready", then use **Inject anomaly**.

## Tests

```bash
cd backend && pytest -q                 # 15 unit tests, < 1 s
python e2e_check.py                     # generator must be running; ~3 min, injects 4 scenarios
```

## Layout

```
generator/log_generator.py       synthetic logs + anomaly injection API
backend/app/ingest/              tailer (rotation-safe), parser + Drain3 templates
backend/app/features/window.py   sliding window with O(1) counters
backend/app/detectors/           EWMA baseline; error-rate, volume, new-template, silence, Isolation Forest
backend/app/alerting/            severity scorer, alert manager (dedup, escalate, resolve, feedback)
backend/app/sinks/               WebSocket hub, AWS (CloudWatch Logs, SNS, metrics)
backend/app/pipeline.py          wires the modules together
backend/app/main.py              FastAPI app: /ws, /api/*
frontend/src/                    React dashboard (useLiveFeed hook + 5 components)
```

See the build guide for how every module works.
