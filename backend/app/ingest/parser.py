import json
import re
import time
from typing import Optional

from ..models import LogEvent

# 2026-09-28T07:33:26.035Z INFO  [payments] Payment ... trace=404fbd2a812f
TEXT_RE = re.compile(
    r"^(?P<ts>\S+)\s+(?P<level>[A-Z]+)\s+\[(?P<service>[^\]]+)\]\s+(?P<msg>.*?)(?:\s+trace=\w+)?$"
)
LEVEL_ALIASES = {"WARNING": "WARN", "ERR": "ERROR", "FATAL": "ERROR", "CRITICAL": "ERROR"}

# Mask variable parts before template mining so Drain sees stable shapes.
MASKS = [
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "<IP>"),
    (re.compile(r"\b[0-9a-f]{8,}\b", re.I), "<HEX>"),
    (re.compile(r"\d+(?:\.\d+)?"), "<NUM>"),
]


def mask(msg: str) -> str:
    for pattern, token in MASKS:
        msg = pattern.sub(token, msg)
    return msg


def parse_line(raw: str) -> Optional[LogEvent]:
    """Turn one raw line (text or JSON) into a LogEvent. Returns None if unparseable."""
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            d = json.loads(raw)
            level = str(d.get("level", "INFO")).upper()
            return LogEvent(ts=time.time(), level=LEVEL_ALIASES.get(level, level),
                            service=d.get("service", "unknown"), msg=d.get("msg", ""), raw=raw)
        except json.JSONDecodeError:
            pass
    m = TEXT_RE.match(raw)
    if not m:
        # Unknown format: keep it, so we never silently drop data.
        level = "ERROR" if re.search(r"\b(error|exception|fatal)\b", raw, re.I) else "INFO"
        return LogEvent(ts=time.time(), level=level, service="unknown", msg=raw, raw=raw)
    level = m["level"].upper()
    return LogEvent(ts=time.time(), level=LEVEL_ALIASES.get(level, level),
                    service=m["service"], msg=m["msg"], raw=raw)


class TemplateEngine:
    """Assigns each message a template id. Uses Drain3 if installed, else a masked-string fallback."""

    def __init__(self):
        try:
            from drain3 import TemplateMiner
            from drain3.template_miner_config import TemplateMinerConfig
            cfg = TemplateMinerConfig()
            cfg.profiling_enabled = False
            self._miner = TemplateMiner(config=cfg)
        except ImportError:
            self._miner = None
            self._ids = {}

    def assign(self, ev: LogEvent) -> LogEvent:
        text = f"{ev.service} {mask(ev.msg)}"   # service prefix: same text in two services = two templates
        if self._miner is not None:
            r = self._miner.add_log_message(text)
            ev.template_id = r["cluster_id"]
            ev.template = r["template_mined"]
            ev.is_new_template = r["change_type"] == "cluster_created"
        else:
            if text not in self._ids:
                self._ids[text] = len(self._ids) + 1
                ev.is_new_template = True
            ev.template_id = self._ids[text]
            ev.template = text
        return ev
