"""FastAPI entry point: starts the pipeline, the AWS sink and the WebSocket hub.

Run from backend/:  uvicorn app.main:app --reload --port 8000
"""
import asyncio
import os
import time
import urllib.request
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .pipeline import Pipeline
from .sinks.aws import AwsSink
from .sinks.websocket import Hub

LOG_PATH = os.getenv("LOG_PATH", "../generator/logs/app.log")
GENERATOR_URL = os.getenv("GENERATOR_URL", "http://localhost:8099")

hub = Hub()
pipeline = Pipeline(
    LOG_PATH,
    window_s=float(os.getenv("WINDOW_S", 60)),
    tick_s=float(os.getenv("TICK_S", 5)),
    warmup_ticks=int(os.getenv("WARMUP_TICKS", 12)),
)


async def on_pushed(alert_id: str, pushed: dict):
    a = pipeline.alerts.mark_pushed(alert_id, pushed)
    if a:
        pushed = a.pushed
    await hub.broadcast({"type": "alert_pushed", "data": {"id": alert_id, **pushed}})


aws = AwsSink(on_pushed=on_pushed)
pipeline.add_listener(hub.broadcast)
pipeline.add_listener(aws.handle)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [asyncio.create_task(c) for c in pipeline.tasks()] + [asyncio.create_task(aws.run())]
    print(f"[main] tailing {os.path.abspath(LOG_PATH)} | AWS {'ON' if aws.enabled else 'mock mode'}")
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Log Anomaly Detector", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await hub.connect(ws, pipeline.snapshot())
    try:
        while True:
            await ws.receive_text()          # we don't expect messages; this just detects disconnects
    except WebSocketDisconnect:
        hub.disconnect(ws)


@app.get("/api/health")
def health():
    return {"ok": True, "lines_total": pipeline.lines_total, "clients": len(hub.clients),
            "aws": "on" if aws.enabled else "mock"}


@app.get("/api/alerts")
def alerts(limit: int = 50):
    return pipeline.alerts.recent(limit)


@app.post("/api/alerts/{alert_id}/ack")
async def ack(alert_id: str):
    a = pipeline.alerts.ack(alert_id)
    if not a:
        raise HTTPException(404, "alert not found")
    await hub.broadcast({"type": "alert", "event": "acked", "data": a.to_dict()})
    return a.to_dict()


@app.post("/api/alerts/{alert_id}/false-positive")
async def false_positive(alert_id: str):
    a = pipeline.alerts.false_positive(alert_id, time.time())
    if not a:
        raise HTTPException(404, "alert not found")
    await hub.broadcast({"type": "alert", "event": "false_positive", "data": a.to_dict()})
    return a.to_dict()


@app.post("/api/inject")
async def inject(scenario: str, service: str = "", duration: int = 30):
    """Proxy to the generator's control API, so the browser only talks to one server."""
    url = f"{GENERATOR_URL}/inject?scenario={scenario}&duration={duration}" + (f"&service={service}" if service else "")
    try:
        body = await asyncio.to_thread(lambda: urllib.request.urlopen(urllib.request.Request(url, method="POST"), timeout=3).read())
    except Exception as e:
        raise HTTPException(502, f"generator not reachable: {e}")
    import json
    return json.loads(body)
