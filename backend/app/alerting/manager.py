import uuid

from ..models import Alert, Finding
from .severity import ORDER, agreement, classify, max_severity


class AlertManager:
    """Turns a stream of findings into a small number of meaningful alerts.

    - fingerprint = detector:metric:service -> one open alert per fingerprint (dedup)
    - persistence = consecutive ticks a fingerprint fires (feeds severity)
    - escalation  = an open alert can only go up in severity while open
    - resolve     = no finding for `resolve_after_s` -> status "resolved"
    - feedback    = ack (stop notifying) / false_positive (mute the fingerprint for a while)
    """

    def __init__(self, resolve_after_s=15.0, mute_s=600.0, update_every_s=10.0):
        self.resolve_after_s = resolve_after_s
        self.mute_s = mute_s
        self.update_every_s = update_every_s
        self.open: dict[str, Alert] = {}
        self.history: list[Alert] = []            # newest last
        self.streak: dict[str, int] = {}
        self.muted_until: dict[str, float] = {}
        self._last_emit: dict[str, float] = {}

    @staticmethod
    def fingerprint(f: Finding) -> str:
        return f"{f.detector}:{f.metric}:{f.service}"

    def process(self, findings: list[Finding], now: float) -> list[tuple[str, Alert]]:
        """Returns events: ("new" | "escalated" | "updated" | "resolved", alert)."""
        events = []
        agree = agreement(findings)
        fired = set()

        for f in findings:
            fp = self.fingerprint(f)
            if self.muted_until.get(fp, 0) > now:
                continue
            fired.add(fp)
            self.streak[fp] = self.streak.get(fp, 0) + 1
            sev = classify(f.score, self.streak[fp], agree.get(f.service, 1))
            alert = self.open.get(fp)

            if alert is None:
                alert = Alert(
                    id=uuid.uuid4().hex[:10], fingerprint=fp, severity=sev, status="open",
                    title=f"{f.detector.replace('_', ' ')} · {'all services' if f.service == '*' else f.service}",
                    reason=f.reason, service=f.service, first_seen=now, last_seen=now,
                    count=1, evidence=list(f.evidence), score=f.score,
                )
                self.open[fp] = alert
                self.history.append(alert)
                self._last_emit[fp] = now
                events.append(("new", alert))
                continue

            alert.count += 1
            alert.last_seen = now
            alert.reason = f.reason
            alert.score = max(alert.score, f.score)
            if f.evidence:
                alert.evidence = (alert.evidence + f.evidence)[-5:]
            new_sev = max_severity(alert.severity, sev)
            if ORDER[new_sev] > ORDER[alert.severity]:
                alert.severity = new_sev
                self._last_emit[fp] = now
                events.append(("escalated", alert))
            elif now - self._last_emit.get(fp, 0) >= self.update_every_s:
                self._last_emit[fp] = now
                events.append(("updated", alert))       # keeps the UI count fresh, never re-notifies AWS

        # Reset streaks for fingerprints that did not fire; resolve quiet alerts.
        for fp in list(self.streak):
            if fp not in fired:
                self.streak[fp] = 0
        for fp, alert in list(self.open.items()):
            if fp not in fired and now - alert.last_seen >= self.resolve_after_s:
                if alert.status == "open":
                    alert.status = "resolved"
                del self.open[fp]
                events.append(("resolved", alert))
        return events

    # ---- operator feedback -------------------------------------------------
    def _find(self, alert_id):
        return next((a for a in reversed(self.history) if a.id == alert_id), None)

    def ack(self, alert_id):
        a = self._find(alert_id)
        if a:
            a.status = "acked"
        return a

    def false_positive(self, alert_id, now):
        a = self._find(alert_id)
        if a:
            a.status = "false_positive"
            self.muted_until[a.fingerprint] = now + self.mute_s
            self.open.pop(a.fingerprint, None)
        return a

    def mark_pushed(self, alert_id, pushed: dict):
        """Remember which AWS sinks accepted this alert, so later events keep the ticks."""
        a = self._find(alert_id)
        if a:
            for k, v in pushed.items():
                a.pushed[k] = a.pushed.get(k, False) or v
        return a

    def recent(self, n=50):
        return [a.to_dict() for a in reversed(self.history[-n:])]
