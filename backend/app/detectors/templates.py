from ..models import Finding, WindowStats


class NewTemplateDetector:
    """Flags log message shapes that were never seen before AND keep repeating.

    Catches brand-new error types that no blacklist knows about. The repeat
    requirement matters: a healthy system has rare-but-normal errors (a card
    declined once a minute) that warm-up may not have seen yet. A one-off new
    line is not an incident; the same new error 3+ times in a window is.
    """

    name = "new_template"

    def __init__(self, warmup_ticks=12, min_repeats=3, min_share=0.005, watch_ticks=12, levels=("ERROR", "WARN")):
        self.warmup_ticks = warmup_ticks
        self.min_repeats = min_repeats
        self.min_share = min_share            # and >= 0.5% of all lines, so it scales with traffic
        self.watch_ticks = watch_ticks        # how long a new template stays "new"
        self.levels = levels
        self.ticks = 0
        self.watching: dict[int, dict] = {}   # template_id -> {"ev": first LogEvent, "age": ticks}

    def evaluate(self, stats: WindowStats) -> list[Finding]:
        self.ticks += 1
        if self.ticks <= self.warmup_ticks:
            return []                         # still learning the normal vocabulary
        for ev in stats.new_templates:
            if ev.level in self.levels:
                self.watching[ev.template_id] = {"ev": ev, "age": 0}

        findings = []
        needed = max(self.min_repeats, self.min_share * stats.total)
        for tid, w in list(self.watching.items()):
            w["age"] += 1
            count = stats.template_counts.get(tid, 0)
            if count >= needed:
                ev = w["ev"]
                findings.append(Finding(
                    detector=self.name, metric=f"template:{tid}", service=ev.service,
                    score=(5.0 if ev.level == "ERROR" else 3.0) + min(count / 10, 2.0),
                    value=count, expected=0,
                    reason=f"New {ev.level} pattern in {ev.service}, seen {count}x: \"{ev.template}\"",
                    evidence=[ev.raw],
                ))
            if w["age"] >= self.watch_ticks:
                del self.watching[tid]        # it has become part of normal vocabulary
        return findings

    def status(self):
        return {"template_learning": self.ticks <= self.warmup_ticks, "watching": len(self.watching)}
