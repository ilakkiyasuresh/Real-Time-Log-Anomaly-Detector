from ..models import Finding, WindowStats
from .baseline import EWMABaseline


class SilenceDetector:
    """A service that normally logs steadily has stopped logging.

    Uses time since the service's last line, compared with its normal gap
    between lines, so it fires within seconds instead of waiting for the
    whole window to drain.
    """

    name = "silence"

    def __init__(self, window_s=60.0, gap_factor=10, min_quiet_s=10.0, min_expected=20, alpha=0.05, warmup=12):
        self.window_s = window_s
        self.gap_factor = gap_factor          # quiet for 10x the normal gap between lines
        self.min_quiet_s = min_quiet_s        # but never less than 10 s
        self.min_expected = min_expected      # only services that normally log >= 20 lines/window
        self.alpha, self.warmup = alpha, warmup
        self.bl: dict[str, EWMABaseline] = {}

    def evaluate(self, stats: WindowStats) -> list[Finding]:
        findings = []
        for svc, s in stats.per_service.items():
            bl = self.bl.setdefault(svc, EWMABaseline(self.alpha, self.warmup, min_std=1.0))
            finding = None
            quiet_for = stats.ts - s["last_seen"]
            if bl.ready and bl.mean >= self.min_expected:
                normal_gap = self.window_s / bl.mean
                limit = max(self.min_quiet_s, self.gap_factor * normal_gap)
                if quiet_for > limit:
                    finding = Finding(
                        detector=self.name, metric="silence", service=svc,
                        score=3.0 + min(quiet_for / limit, 3.0),   # grows the longer it stays quiet
                        value=quiet_for, expected=normal_gap,
                        reason=f"{svc} has not logged for {quiet_for:.0f}s (normally a line every {normal_gap:.1f}s)",
                    )
                    findings.append(finding)
            bl.update(s["total"], anomalous=finding is not None)
        return findings

    def status(self):
        return {}
