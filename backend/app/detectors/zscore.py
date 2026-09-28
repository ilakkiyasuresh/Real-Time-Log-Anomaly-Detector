from ..models import Finding, WindowStats
from .baseline import EWMABaseline


class ErrorRateDetector:
    """z-score on the global error rate and on each service's error rate."""

    name = "error_rate"

    def __init__(self, z_threshold=3.0, alpha=0.05, warmup=12, min_errors=5):
        self.z_threshold = z_threshold
        self.alpha, self.warmup = alpha, warmup
        self.min_errors = min_errors      # ignore tiny counts (1 error in 3 lines = 33%)
        self.global_bl = EWMABaseline(alpha, warmup, min_std=0.01)
        self.svc_bl: dict[str, EWMABaseline] = {}

    def evaluate(self, stats: WindowStats) -> list[Finding]:
        findings = []
        f = self._check(self.global_bl, stats.error_rate, stats.errors, "*", stats)
        if f:
            findings.append(f)
        for svc, s in stats.per_service.items():
            bl = self.svc_bl.setdefault(svc, EWMABaseline(self.alpha, self.warmup, min_std=0.01))
            f = self._check(bl, s["error_rate"], s["errors"], svc, stats)
            if f:
                findings.append(f)
        return findings

    def _check(self, bl, value, errors, service, stats):
        finding = None
        if bl.ready and errors >= self.min_errors:
            z = bl.zscore(value)
            if z >= self.z_threshold:
                where = "overall" if service == "*" else f"in {service}"
                finding = Finding(
                    detector=self.name, metric="error_rate", service=service, score=z,
                    value=value, expected=bl.mean,
                    reason=f"Error rate {where} is {value:.1%} vs normal {bl.mean:.1%} ({z:.1f}σ above)",
                    evidence=stats.samples.get(service, [])[-3:] if service != "*" else
                    [l for v in stats.samples.values() for l in v][-3:],
                )
        bl.update(value, anomalous=finding is not None)
        return finding

    def status(self):
        lo, hi = self.global_bl.band()
        return {"error_rate_mean": self.global_bl.mean, "error_rate_std": self.global_bl.std,
                "band": [lo, hi], "ready": self.global_bl.ready,
                "warmup_left": max(0, self.global_bl.warmup - self.global_bl.n)}


class VolumeDetector:
    """z-score on total lines per window, both directions (spike and drop)."""

    name = "volume"

    def __init__(self, z_threshold=4.0, alpha=0.05, warmup=12):
        self.z_threshold = z_threshold
        self.bl = EWMABaseline(alpha, warmup, min_std=1.0)

    def evaluate(self, stats: WindowStats) -> list[Finding]:
        finding = None
        # Floor sigma at 5% of the mean so a very steady stream doesn't make small wobbles look huge.
        if self.bl.ready:
            std = max(self.bl.std, 0.05 * abs(self.bl.mean))
            z = (stats.total - self.bl.mean) / std
            if abs(z) >= self.z_threshold:
                direction = "spike" if z > 0 else "drop"
                finding = Finding(
                    detector=self.name, metric=f"volume_{direction}", service="*", score=abs(z),
                    value=stats.total, expected=self.bl.mean,
                    reason=f"Log volume {direction}: {stats.total} lines/window vs normal {self.bl.mean:.0f}",
                )
        self.bl.update(stats.total, anomalous=finding is not None)
        return [finding] if finding else []

    def status(self):
        return {"volume_mean": self.bl.mean}
