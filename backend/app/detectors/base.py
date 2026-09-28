from typing import Protocol

from ..models import Finding, WindowStats


class Detector(Protocol):
    name: str

    def evaluate(self, stats: WindowStats) -> list[Finding]:
        """Look at one tick of window stats, return zero or more findings.

        Detectors own their baselines and update them inside evaluate().
        """
        ...

    def status(self) -> dict:
        """Optional: baseline info for the dashboard."""
        ...


REGISTRY: list = []


def register(detector):
    REGISTRY.append(detector)
    return detector
