from collections import Counter, deque

from ..models import LogEvent, WindowStats


class SlidingWindow:
    """Keeps the last `size_s` seconds of events with O(1) running counters.

    add() increments counters; evict() pops expired events from the left and
    decrements them. snapshot() is therefore cheap no matter how busy the log is.
    """

    def __init__(self, size_s: float = 60.0):
        self.size_s = size_s
        self.events: deque = deque()
        self.total = 0
        self.by_level = Counter()
        self.svc_total = Counter()
        self.svc_errors = Counter()
        self.templates = Counter()
        self.new_since_tick: list = []
        self.samples: dict = {}
        self.last_seen: dict = {}

    def add(self, ev: LogEvent) -> None:
        self.events.append(ev)
        self.total += 1
        self.by_level[ev.level] += 1
        self.svc_total[ev.service] += 1
        self.last_seen[ev.service] = ev.ts
        if ev.level == "ERROR":
            self.svc_errors[ev.service] += 1
            self.samples.setdefault(ev.service, deque(maxlen=5)).append(ev.raw)
        if ev.template_id is not None:
            self.templates[ev.template_id] += 1
        if ev.is_new_template:
            self.new_since_tick.append(ev)

    def evict(self, now: float) -> None:
        cutoff = now - self.size_s
        while self.events and self.events[0].ts < cutoff:
            ev = self.events.popleft()
            self.total -= 1
            self.by_level[ev.level] -= 1
            self.svc_total[ev.service] -= 1
            if ev.level == "ERROR":
                self.svc_errors[ev.service] -= 1
            if ev.template_id is not None:
                self.templates[ev.template_id] -= 1
                if self.templates[ev.template_id] <= 0:
                    del self.templates[ev.template_id]

    def snapshot(self, now: float, services_seen: set) -> WindowStats:
        self.evict(now)
        per_service = {}
        for svc in services_seen:          # include services with 0 lines (needed for silence detection)
            t, e = self.svc_total[svc], self.svc_errors[svc]
            per_service[svc] = {"total": t, "errors": e, "error_rate": e / t if t else 0.0,
                                "last_seen": self.last_seen.get(svc, 0.0)}
        errors = self.by_level["ERROR"]
        stats = WindowStats(
            ts=now,
            total=self.total,
            errors=errors,
            warns=self.by_level["WARN"],
            error_rate=errors / self.total if self.total else 0.0,
            per_service=per_service,
            template_counts=dict(self.templates),
            new_templates=self.new_since_tick,
            samples={k: list(v) for k, v in self.samples.items()},
        )
        self.new_since_tick = []
        return stats
