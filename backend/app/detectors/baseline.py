import math


class EWMABaseline:
    """Adaptive baseline: exponentially weighted mean and variance of one metric."""

    def __init__(self, alpha: float = 0.05, warmup: int = 12, min_std: float = 0.01):
        self.alpha = alpha
        self.warmup = warmup          # ticks before we trust it
        self.min_std = min_std        # floor so flat metrics don't explode z-scores
        self.mean = None
        self.var = 0.0
        self.n = 0

    @property
    def ready(self) -> bool:
        return self.n >= self.warmup

    @property
    def std(self) -> float:
        return max(math.sqrt(self.var), self.min_std)

    def zscore(self, x: float) -> float:
        if self.mean is None:
            return 0.0
        return (x - self.mean) / self.std

    def update(self, x: float, anomalous: bool = False) -> None:
        if self.mean is None:
            self.mean, self.n = x, 1
            return
        d = x - self.mean
        if anomalous:
            # During an incident: nudge the mean 10x slower and freeze the variance,
            # so the incident doesn't become the new "normal" (baseline poisoning).
            self.mean += self.alpha * 0.1 * d
            return
        a = self.alpha
        self.mean += a * d
        self.var = (1 - a) * (self.var + a * d * d)
        self.n += 1

    def band(self, k: float = 3.0):
        """(lower, upper) for the dashboard's shaded band."""
        if self.mean is None:
            return (0.0, 0.0)
        return (max(0.0, self.mean - k * self.std), self.mean + k * self.std)

    def to_dict(self):
        return {"mean": self.mean, "var": self.var, "n": self.n}

    def load(self, d):
        self.mean, self.var, self.n = d["mean"], d["var"], d["n"]
