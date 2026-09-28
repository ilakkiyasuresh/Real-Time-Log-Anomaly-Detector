import asyncio
import time
from collections import deque

from .alerting.manager import AlertManager
from .detectors.silence import SilenceDetector
from .detectors.templates import NewTemplateDetector
from .detectors.zscore import ErrorRateDetector, VolumeDetector
from .features.window import SlidingWindow
from .ingest.parser import TemplateEngine, parse_line
from .ingest.tailer import tail


class Pipeline:
    """Tailer -> parser -> window -> detectors -> alert manager -> listeners.

    Listeners are async callables `fn(message: dict)`; the WebSocket hub and
    AWS sinks register themselves with add_listener().
    """

    def __init__(self, log_path, window_s=60.0, tick_s=5.0, warmup_ticks=12, alpha=0.05):
        self.log_path = log_path
        self.tick_s = tick_s
        self.window = SlidingWindow(window_s)
        self.templates = TemplateEngine()
        self.detectors = [
            ErrorRateDetector(alpha=alpha, warmup=warmup_ticks),
            VolumeDetector(alpha=alpha, warmup=warmup_ticks),
            NewTemplateDetector(warmup_ticks=warmup_ticks),
            SilenceDetector(window_s=window_s, alpha=alpha, warmup=warmup_ticks),
        ]
        self.alerts = AlertManager()
        self.services: set = set()
        self.listeners: list = []
        self.recent_logs = deque(maxlen=200)
        self.recent_metrics = deque(maxlen=360)
        self._log_buffer: list = []
        self.lines_total = 0
        self.started = None

    def add_listener(self, fn):
        self.listeners.append(fn)

    async def emit(self, msg: dict):
        for fn in self.listeners:
            try:
                await fn(msg)
            except Exception as e:           # one broken sink must never stop detection
                print(f"[pipeline] listener error: {e!r}")

    async def ingest_loop(self):
        self.started = time.time()
        async for raw in tail(self.log_path):
            ev = parse_line(raw)
            if ev is None:
                continue
            self.templates.assign(ev)
            self.services.add(ev.service)
            self.window.add(ev)
            self.lines_total += 1
            item = {"ts": ev.ts, "level": ev.level, "service": ev.service, "msg": ev.msg,
                    "template_id": ev.template_id}
            self.recent_logs.append(item)
            self._log_buffer.append(item)

    async def flush_logs_loop(self, every_s=0.25):
        """Send logs to the UI in small batches: smooth, and survives a 5x traffic spike."""
        while True:
            await asyncio.sleep(every_s)
            if self._log_buffer:
                batch, self._log_buffer = self._log_buffer, []
                await self.emit({"type": "log_batch", "data": batch})

    async def tick_loop(self):
        while True:
            await asyncio.sleep(self.tick_s)
            await self.tick(time.time())

    async def tick(self, now: float):
        stats = self.window.snapshot(now, self.services)
        # Don't learn from a half-empty window: until one full window has passed,
        # totals are still climbing from zero and would poison every baseline.
        window_full = self.started is not None and now - self.started >= self.window.size_s
        findings = []
        if window_full:
            for d in self.detectors:
                findings.extend(d.evaluate(stats))
        base = self.detectors[0].status()
        metric = {
            "ts": now, "error_rate": stats.error_rate, "total": stats.total, "errors": stats.errors,
            "baseline_mean": base["error_rate_mean"], "band": base["band"],
            "baseline_ready": window_full and base["ready"],
            "warmup_left": base["warmup_left"] + (0 if window_full else 1),
            "per_service": {k: {"error_rate": v["error_rate"], "total": v["total"]}
                            for k, v in stats.per_service.items()},
            "anomalous": bool(findings),
        }
        self.recent_metrics.append(metric)
        await self.emit({"type": "metric", "data": metric})
        for kind, alert in self.alerts.process(findings, now):
            await self.emit({"type": "alert", "event": kind, "data": alert.to_dict()})

    def snapshot(self):
        """Everything a newly connected dashboard needs to draw immediately."""
        return {"logs": list(self.recent_logs), "metrics": list(self.recent_metrics),
                "alerts": self.alerts.recent()}

    def tasks(self):
        return [self.ingest_loop(), self.tick_loop(), self.flush_logs_loop()]
