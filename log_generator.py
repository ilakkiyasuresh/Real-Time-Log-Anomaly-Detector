#!/usr/bin/env python3
"""
Synthetic live log generator with on-demand anomaly injection.

Appends realistic log lines to a growing file, and exposes a tiny HTTP
control API so the dashboard (or curl) can inject anomalies live.

Usage:
    python log_generator.py                       # writes logs/app.log, control API on :8099
    python log_generator.py --rate 20 --format json
    python log_generator.py --auto 90             # auto-inject a random scenario every ~90s

Control API (CORS enabled, so a React button can call it directly):
    GET  /status                                  -> current rate, active scenarios
    GET  /scenarios                               -> list of available scenarios
    POST /inject?scenario=error_burst&service=payments&duration=30
    POST /reset                                   -> clear all active scenarios

Stdlib only; no dependencies.
"""

import argparse
import json
import math
import os
import random
import string
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# --------------------------------------------------------------------------
# Log content: services and templates
# --------------------------------------------------------------------------

def _ip():
    return f"10.0.{random.randint(0, 9)}.{random.randint(1, 254)}"

def _id(n=5):
    return random.randint(10 ** (n - 1), 10 ** n - 1)

def _trace():
    return "".join(random.choices(string.hexdigits.lower(), k=12))

def _ms(lo=5, hi=250):
    return random.randint(lo, hi)

SERVICES = {
    "auth": {
        "weight": 3,
        "INFO": [
            lambda: f"User {_id()} logged in from {_ip()}",
            lambda: f"Token refreshed for user {_id()}",
            lambda: f"Session {_trace()} created in {_ms()}ms",
        ],
        "WARN": [
            lambda: f"Failed login attempt for user {_id()} from {_ip()}",
            lambda: f"Token near expiry for user {_id()}",
        ],
        "ERROR": [
            lambda: f"Authentication service unreachable after {_ms(1000, 5000)}ms",
            lambda: f"Invalid signature on token for user {_id()}",
        ],
    },
    "payments": {
        "weight": 2,
        "INFO": [
            lambda: f"Payment {_id(8)} authorized for order {_id()} in {_ms()}ms",
            lambda: f"Refund {_id(8)} processed for order {_id()}",
        ],
        "WARN": [
            lambda: f"Payment gateway slow response {_ms(800, 2000)}ms for order {_id()}",
            lambda: f"Retrying payment {_id(8)} attempt {random.randint(2, 3)}",
        ],
        "ERROR": [
            lambda: f"Payment timeout after 3000ms for order {_id()}",
            lambda: f"Card declined by issuer for payment {_id(8)} code={random.choice(['05', '51', '54'])}",
        ],
    },
    "orders": {
        "weight": 4,
        "INFO": [
            lambda: f"Order {_id()} created with {random.randint(1, 6)} items",
            lambda: f"Order {_id()} shipped via {random.choice(['DHL', 'BlueDart', 'Delhivery'])}",
            lambda: f"GET /api/orders/{_id()} 200 {_ms()}ms",
        ],
        "WARN": [
            lambda: f"Inventory low for SKU-{_id(4)} remaining={random.randint(1, 5)}",
            lambda: f"GET /api/orders/{_id()} 404 {_ms()}ms",
        ],
        "ERROR": [
            lambda: f"Database query failed on orders table: deadlock detected",
            lambda: f"GET /api/orders/{_id()} 500 {_ms(300, 900)}ms",
        ],
    },
    "gateway": {
        "weight": 5,
        "INFO": [
            lambda: f"{random.choice(['GET', 'POST'])} /api/{random.choice(['cart', 'search', 'profile'])} 200 {_ms()}ms from {_ip()}",
            lambda: f"Health check passed upstream={random.choice(['auth', 'orders', 'payments'])}",
        ],
        "WARN": [
            lambda: f"Rate limit approaching for client {_ip()}",
            lambda: f"Upstream {random.choice(['auth', 'orders'])} latency {_ms(500, 1500)}ms",
        ],
        "ERROR": [
            lambda: f"502 Bad Gateway upstream={random.choice(['auth', 'orders', 'payments'])}",
            lambda: f"Circuit breaker OPEN for upstream {random.choice(['payments', 'orders'])}",
        ],
    },
}

# Brand-new error types that never appear in normal traffic.
# Used by the `new_exception` scenario to test template-drift detection.
NOVEL_ERRORS = [
    lambda: f"java.lang.OutOfMemoryError: Java heap space in worker-{random.randint(1, 8)}",
    lambda: f"SSL handshake failed: certificate expired for host api.partner-{random.randint(1, 3)}.com",
    lambda: f"Disk quota exceeded on /var/data volume vol-{_id(6)}",
    lambda: f"Kafka consumer group rebalancing: partition {random.randint(0, 11)} lost",
]

BASE_LEVEL_PROBS = {"INFO": 0.95, "WARN": 0.04, "ERROR": 0.01}

# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------

SCENARIOS = {
    "error_burst":   "Sudden jump in error rate for one service (default 40% errors)",
    "error_creep":   "Error rate rises gradually over the duration (slow-burn incident)",
    "new_exception": "A never-before-seen error type starts appearing",
    "silence":       "A service stops logging entirely (dead heartbeat)",
    "traffic_spike": "Overall log volume jumps ~5x (DDoS / viral traffic)",
    "latency":       "One service logs many slow-response warnings",
}


@dataclass
class ActiveScenario:
    name: str
    service: str
    started: float
    duration: float
    extra: dict = field(default_factory=dict)

    def progress(self, now):
        return min(1.0, (now - self.started) / self.duration) if self.duration else 1.0

    def expired(self, now):
        return now - self.started >= self.duration

    def to_dict(self, now):
        return {
            "scenario": self.name,
            "service": self.service,
            "elapsed_s": round(now - self.started, 1),
            "duration_s": self.duration,
            **self.extra,
        }


class Generator:
    def __init__(self, path, rate, fmt, rotate_mb, seed=None):
        self.path = path
        self.base_rate = rate
        self.fmt = fmt
        self.rotate_bytes = int(rotate_mb * 1024 * 1024) if rotate_mb else 0
        self.active: list[ActiveScenario] = []
        self.lock = threading.Lock()
        self.lines_written = 0
        self.started = time.time()
        if seed is not None:
            random.seed(seed)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.fh = open(path, "a", buffering=1)  # line-buffered so tailers see lines immediately

    # ---- scenario management -------------------------------------------

    def inject(self, name, service=None, duration=30.0, **extra):
        if name not in SCENARIOS:
            raise ValueError(f"unknown scenario '{name}'. Options: {', '.join(SCENARIOS)}")
        if service is None or service not in SERVICES:
            service = random.choice(list(SERVICES))
        sc = ActiveScenario(name, service, time.time(), float(duration), extra)
        if name == "new_exception":
            sc.extra["template"] = random.randrange(len(NOVEL_ERRORS))
        with self.lock:
            self.active.append(sc)
        self._marker(f"inject {name} service={service} duration={duration}s")
        return sc

    def reset(self):
        with self.lock:
            self.active.clear()
        self._marker("reset all scenarios")

    def status(self):
        now = time.time()
        with self.lock:
            return {
                "file": os.path.abspath(self.path),
                "base_rate_per_s": self.base_rate,
                "current_rate_per_s": round(self._rate(now), 2),
                "lines_written": self.lines_written,
                "uptime_s": round(now - self.started, 1),
                "active": [s.to_dict(now) for s in self.active],
            }

    def _marker(self, text):
        # Ground-truth marker printed to the console (NOT the log file),
        # so you can compare what was injected vs what the detector caught.
        print(f"[generator {datetime.now().strftime('%H:%M:%S')}] {text}", flush=True)

    # ---- generation ----------------------------------------------------

    def _rate(self, now):
        # Gentle sinusoidal drift so the baseline isn't perfectly flat.
        rate = self.base_rate * (1 + 0.15 * math.sin((now - self.started) / 120 * 2 * math.pi))
        for s in self.active:
            if s.name == "traffic_spike":
                rate *= float(s.extra.get("multiplier", 5))
        return rate

    def _pick_service(self):
        silenced = {s.service for s in self.active if s.name == "silence"}
        choices = [(n, c["weight"]) for n, c in SERVICES.items() if n not in silenced]
        names, weights = zip(*choices) if choices else ([], [])
        return random.choices(names, weights=weights)[0] if names else None

    def _level_probs(self, service, now):
        probs = dict(BASE_LEVEL_PROBS)
        for s in self.active:
            if s.service != service:
                continue
            if s.name == "error_burst":
                p = float(s.extra.get("error_rate", 0.4))
                probs = {"INFO": (1 - p) * 0.9, "WARN": (1 - p) * 0.1, "ERROR": p}
            elif s.name == "error_creep":
                p = 0.01 + s.progress(now) * float(s.extra.get("max_error_rate", 0.3))
                probs = {"INFO": (1 - p) * 0.93, "WARN": (1 - p) * 0.07, "ERROR": p}
            elif s.name == "latency":
                probs = {"INFO": 0.55, "WARN": 0.42, "ERROR": 0.03}
        return probs

    def _make_line(self, now):
        service = self._pick_service()
        if service is None:
            return None

        # new_exception: some of this service's lines become the novel error
        for s in self.active:
            if s.name == "new_exception" and s.service == service and random.random() < 0.25:
                return self._format(now, "ERROR", service, NOVEL_ERRORS[s.extra["template"]]())

        probs = self._level_probs(service, now)
        level = random.choices(list(probs), weights=list(probs.values()))[0]

        if level == "WARN" and any(s.name == "latency" and s.service == service for s in self.active):
            msg = f"Slow response {_ms(1500, 6000)}ms on /api/{service}/{_id()}"
        else:
            msg = random.choice(SERVICES[service][level])()
        return self._format(now, level, service, msg)

    def _format(self, now, level, service, msg):
        ts = datetime.fromtimestamp(now, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        trace = _trace()
        if self.fmt == "json":
            return json.dumps({"ts": ts, "level": level, "service": service, "msg": msg, "trace": trace})
        return f"{ts} {level:<5} [{service}] {msg} trace={trace}"

    def _maybe_rotate(self):
        if not self.rotate_bytes:
            return
        if self.fh.tell() >= self.rotate_bytes:
            self.fh.close()
            os.replace(self.path, self.path + ".1")
            self.fh = open(self.path, "a", buffering=1)
            self._marker(f"rotated log -> {self.path}.1")

    def run(self, stop_event):
        next_t = time.time()
        while not stop_event.is_set():
            now = time.time()
            with self.lock:
                expired = [s for s in self.active if s.expired(now)]
                self.active = [s for s in self.active if not s.expired(now)]
                rate = self._rate(now)
                line = self._make_line(now)
            for s in expired:
                self._marker(f"ended {s.name} service={s.service}")
            if line:
                self.fh.write(line + "\n")
                self.lines_written += 1
                self._maybe_rotate()
            # Poisson arrivals: exponential gaps give realistic bursty timing
            next_t += random.expovariate(max(rate, 0.01))
            sleep = next_t - time.time()
            if sleep > 0:
                stop_event.wait(sleep)
            elif sleep < -1:
                next_t = time.time()  # fell behind; don't try to catch up in a flood
        self.fh.close()


# --------------------------------------------------------------------------
# HTTP control API
# --------------------------------------------------------------------------

def make_handler(gen: Generator):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body):
            data = json.dumps(body, indent=2).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self._send(204, {})

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/status":
                self._send(200, gen.status())
            elif path == "/scenarios":
                self._send(200, {"scenarios": SCENARIOS, "services": list(SERVICES)})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/inject":
                    name = q.pop("scenario", None)
                    if not name:
                        return self._send(400, {"error": "scenario is required", "options": list(SCENARIOS)})
                    service = q.pop("service", None)
                    duration = float(q.pop("duration", 30))
                    sc = gen.inject(name, service, duration, **q)
                    self._send(200, {"injected": sc.to_dict(time.time())})
                elif url.path == "/reset":
                    gen.reset()
                    self._send(200, {"ok": True})
                else:
                    self._send(404, {"error": "not found"})
            except ValueError as e:
                self._send(400, {"error": str(e)})

        def log_message(self, *args):
            pass  # keep the console clean for injection markers

    return Handler


def auto_injector(gen, interval, stop_event):
    # Waits one interval first so the detector can learn a baseline.
    while not stop_event.wait(random.uniform(interval * 0.7, interval * 1.3)):
        name = random.choice(list(SCENARIOS))
        gen.inject(name, duration=random.choice([20, 30, 45]))


def main():
    ap = argparse.ArgumentParser(description="Synthetic live log generator with anomaly injection")
    ap.add_argument("--file", default="logs/app.log", help="log file to append to")
    ap.add_argument("--rate", type=float, default=10, help="average lines per second in normal traffic")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument("--port", type=int, default=8099, help="control API port (0 to disable)")
    ap.add_argument("--auto", type=float, default=0, help="auto-inject a random scenario every ~N seconds")
    ap.add_argument("--rotate-mb", type=float, default=0, help="rotate log at this size (tests tailer rotation)")
    ap.add_argument("--seed", type=int, default=None, help="random seed for reproducible runs")
    args = ap.parse_args()

    gen = Generator(args.file, args.rate, args.format, args.rotate_mb, args.seed)
    stop = threading.Event()

    if args.port:
        server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(gen))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f"Control API on http://localhost:{args.port}  (GET /status, /scenarios; POST /inject, /reset)")
    if args.auto:
        threading.Thread(target=auto_injector, args=(gen, args.auto, stop), daemon=True).start()
        print(f"Auto-injecting a random scenario every ~{args.auto:.0f}s")

    print(f"Writing ~{args.rate}/s lines to {os.path.abspath(args.file)}  (Ctrl+C to stop)")
    try:
        gen.run(stop)
    except KeyboardInterrupt:
        stop.set()
        print("\nstopped.")


if __name__ == "__main__":
    main()
