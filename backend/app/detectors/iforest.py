import numpy as np

from ..models import Finding, WindowStats


class IsolationForestDetector:
    """Multivariate detector: learns what a normal *combination* of features looks like.

    Useful for anomalies that no single metric shows clearly, e.g. volume a bit
    high AND warnings a bit high AND template diversity a bit low at once.
    Needs scikit-learn. Trains on the first `train_ticks` windows, retrains
    every `retrain_every` ticks on recent normal windows.
    """

    name = "isolation_forest"

    def __init__(self, train_ticks=60, retrain_every=120, contamination=0.01, threshold=0.0):
        from sklearn.ensemble import IsolationForest  # imported here so the rest works without sklearn
        self._IF = IsolationForest
        self.train_ticks = train_ticks
        self.retrain_every = retrain_every
        self.contamination = contamination
        self.threshold = threshold          # decision_function < threshold -> anomaly
        self.history: list = []
        self.model = None
        self.ticks = 0
        self.streak = 0                     # require 2 unusual ticks in a row (cuts false alarms)

    @staticmethod
    def features(s: WindowStats) -> list[float]:
        warn_rate = s.warns / s.total if s.total else 0.0
        return [
            s.total,
            s.error_rate,
            warn_rate,
            len(s.template_counts),                                   # template diversity
            max((v["error_rate"] for v in s.per_service.values()), default=0.0),
        ]

    def _fit(self):
        X = np.array(self.history[-500:])
        self.model = self._IF(n_estimators=100, contamination=self.contamination, random_state=0).fit(X)

    def evaluate(self, stats: WindowStats) -> list[Finding]:
        self.ticks += 1
        x = self.features(stats)
        if self.model is None:
            self.history.append(x)
            if len(self.history) >= self.train_ticks:
                self._fit()
            return []
        score = float(self.model.decision_function([x])[0])   # > 0 normal, < 0 unusual
        if score < self.threshold:
            self.streak += 1
            if self.streak < 2:
                return []
            return [Finding(
                detector=self.name, metric="multivariate", service="*",
                score=3.0, value=score, expected=0.0,
                reason=f"Unusual combination: volume={x[0]:.0f}, errors={x[1]:.1%}, "
                       f"warnings={x[2]:.1%}, templates={x[3]:.0f} (score {score:.2f})",
            )]
        self.streak = 0
        self.history.append(x)                                   # only learn from normal windows
        if self.ticks % self.retrain_every == 0:
            self._fit()
        return []

    def status(self):
        return {"iforest_trained": self.model is not None}
