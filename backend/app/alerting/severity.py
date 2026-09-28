from collections import defaultdict

from ..models import Finding

ORDER = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}


def agreement(findings: list[Finding]) -> dict:
    """service -> number of distinct detectors firing for it (global '*' findings count for everyone)."""
    per_svc = defaultdict(set)
    global_dets = {f.detector for f in findings if f.service == "*"}
    for f in findings:
        per_svc[f.service].add(f.detector)
    return {svc: len(dets | global_dets) for svc, dets in per_svc.items()}


def classify(score: float, persistence: int, agree: int) -> str:
    """Three signals -> one severity.

    score        how far from normal (z-score or equivalent)
    persistence  how many consecutive ticks this fingerprint has fired
    agree        how many different detectors see a problem in the same place
    """
    if score >= 6 or (score >= 4 and persistence >= 3) or agree >= 3:
        return "CRITICAL"
    if score >= 4 or persistence >= 3 or agree >= 2:
        return "WARNING"
    return "INFO"


def max_severity(a: str, b: str) -> str:
    return a if ORDER[a] >= ORDER[b] else b
