from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class LogEvent:            # tailer + parser -> feature engine
    ts: float              # unix seconds (ingest time)
    level: str             # INFO | WARN | ERROR
    service: str
    msg: str
    template_id: Optional[int] = None
    template: Optional[str] = None
    is_new_template: bool = False
    raw: str = ""


@dataclass
class WindowStats:         # feature engine -> detectors, every tick
    ts: float
    total: int
    errors: int
    warns: int
    error_rate: float
    per_service: dict      # service -> {"total": n, "errors": n, "error_rate": r}
    template_counts: dict  # template_id -> count in window
    new_templates: list    # LogEvents whose template appeared for the first time this tick
    samples: dict = field(default_factory=dict)  # service -> last few ERROR raw lines


@dataclass
class Finding:             # detector -> severity scorer
    detector: str
    metric: str
    service: str
    score: float
    value: float
    expected: float
    reason: str
    evidence: list = field(default_factory=list)


@dataclass
class Alert:               # alert manager -> sinks
    id: str
    fingerprint: str
    severity: str          # INFO | WARNING | CRITICAL
    status: str            # open | resolved | acked | false_positive
    title: str
    reason: str
    service: str
    first_seen: float
    last_seen: float
    count: int
    evidence: list
    score: float = 0.0
    pushed: dict = field(default_factory=lambda: {"cloudwatch": False, "sns": False})

    def to_dict(self):
        return asdict(self)
