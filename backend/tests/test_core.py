"""Fast unit tests for the core modules. Run from backend/:  pytest -q"""
import asyncio
import os

from app.alerting.manager import AlertManager
from app.alerting.severity import classify
from app.detectors.baseline import EWMABaseline
from app.detectors.silence import SilenceDetector
from app.detectors.templates import NewTemplateDetector
from app.detectors.zscore import ErrorRateDetector
from app.features.window import SlidingWindow
from app.ingest.parser import TemplateEngine, mask, parse_line
from app.ingest.tailer import tail
from app.models import Finding, LogEvent, WindowStats


def ev(ts, level="INFO", service="svc", tid=None, new=False, raw="x"):
    return LogEvent(ts=ts, level=level, service=service, msg="m", template_id=tid, is_new_template=new, raw=raw)


def stats(**kw):
    base = dict(ts=0, total=600, errors=6, warns=0, error_rate=0.01, per_service={},
                template_counts={}, new_templates=[], samples={})
    base.update(kw)
    return WindowStats(**base)


# ---- parser ------------------------------------------------------------------
def test_parse_text_line():
    e = parse_line("2026-09-28T07:33:26.035Z ERROR [payments] Payment timeout after 3000ms for order 1 trace=abc123")
    assert (e.level, e.service, e.msg) == ("ERROR", "payments", "Payment timeout after 3000ms for order 1")


def test_parse_json_and_alias():
    e = parse_line('{"level": "warning", "service": "auth", "msg": "slow"}')
    assert (e.level, e.service) == ("WARN", "auth")


def test_unknown_format_is_kept_not_dropped():
    e = parse_line("Traceback: something exploded with an Exception")
    assert e is not None and e.level == "ERROR" and e.service == "unknown"


def test_mask_and_templates():
    assert mask("user 42 from 10.0.0.1") == "user <NUM> from <IP>"
    t = TemplateEngine()
    a = t.assign(parse_line("2026-01-01T00:00:00Z INFO [s] Order 123 created"))
    b = t.assign(parse_line("2026-01-01T00:00:00Z INFO [s] Order 999 created"))
    assert a.template_id == b.template_id and a.is_new_template and not b.is_new_template


# ---- sliding window -------------------------------------------------------------
def test_window_counts_and_eviction():
    w = SlidingWindow(size_s=10)
    for t in range(20):
        w.add(ev(t, level="ERROR" if t % 5 == 0 else "INFO", tid=1))
    s = w.snapshot(now=19.5, services_seen={"svc"})
    assert s.total == 10                   # only t = 10..19 remain
    assert s.errors == 2                   # t = 10, 15
    assert abs(s.error_rate - 0.2) < 1e-9
    assert s.template_counts == {1: 10}


def test_window_lists_silent_services():
    w = SlidingWindow(size_s=10)
    w.add(ev(0, service="a"))
    s = w.snapshot(now=50, services_seen={"a", "b"})
    assert s.per_service["b"]["total"] == 0


# ---- baseline -------------------------------------------------------------------
def test_ewma_converges_and_zscore():
    b = EWMABaseline(alpha=0.1, warmup=5, min_std=0.001)
    for i in range(200):
        b.update(10 + (1 if i % 2 else -1))
    assert b.ready and abs(b.mean - 10) < 0.2
    assert b.zscore(20) > 5


def test_anomalous_updates_do_not_poison():
    b = EWMABaseline(alpha=0.1, warmup=5)
    for _ in range(50):
        b.update(1.0)
    for _ in range(20):
        b.update(100.0, anomalous=True)
    assert b.mean < 60                     # full-speed learning would be ~88


# ---- detectors ------------------------------------------------------------------
def test_error_rate_detector_fires_on_burst():
    d = ErrorRateDetector(warmup=5)
    ps = lambda r: {"payments": {"total": 100, "errors": int(r * 100), "error_rate": r, "last_seen": 0}}
    for _ in range(20):
        assert d.evaluate(stats(error_rate=0.01, errors=6, per_service=ps(0.01))) == []
    f = d.evaluate(stats(error_rate=0.08, errors=48, per_service=ps(0.4)))
    assert {x.service for x in f} == {"*", "payments"}


def test_new_template_needs_repeats():
    d = NewTemplateDetector(warmup_ticks=2, min_repeats=3)
    d.evaluate(stats()); d.evaluate(stats())
    new = ev(0, level="ERROR", tid=77, new=True)
    assert d.evaluate(stats(new_templates=[new], template_counts={77: 1})) == []   # one-off: ignore
    assert len(d.evaluate(stats(template_counts={77: 5}))) == 1                     # repeats: alert


def test_silence_detector():
    d = SilenceDetector(window_s=60, warmup=3)
    for t in range(10):
        assert d.evaluate(stats(ts=t, per_service={"gw": {"total": 300, "errors": 0, "error_rate": 0, "last_seen": t}})) == []
    f = d.evaluate(stats(ts=100, per_service={"gw": {"total": 50, "errors": 0, "error_rate": 0, "last_seen": 80}}))
    assert f and f[0].service == "gw"


# ---- severity and alert manager ---------------------------------------------------
def test_classify():
    assert classify(3.1, 1, 1) == "INFO"
    assert classify(4.5, 1, 1) == "WARNING"
    assert classify(4.5, 3, 1) == "CRITICAL"
    assert classify(3.1, 1, 3) == "CRITICAL"


def test_manager_dedups_escalates_resolves():
    m = AlertManager(resolve_after_s=10)
    f = lambda z: Finding("error_rate", "error_rate", "payments", z, 0.3, 0.01, "r")
    e1 = m.process([f(4.2)], now=0)
    e2 = m.process([f(4.2)], now=2)
    e3 = m.process([f(4.2)], now=4)        # 3rd tick in a row -> CRITICAL
    assert [k for k, _ in e1] == ["new"] and e2 == [] and [k for k, _ in e3] == ["escalated"]
    assert len(m.history) == 1 and m.history[0].count == 3
    assert [k for k, _ in m.process([], now=20)] == ["resolved"]


def test_false_positive_mutes():
    m = AlertManager()
    f = Finding("volume", "volume_spike", "*", 5, 1, 1, "r")
    a = m.process([f], now=0)[0][1]
    m.false_positive(a.id, now=1)
    assert m.process([f], now=2) == []


# ---- tailer ---------------------------------------------------------------------
def test_tailer_follows_rotation(tmp_path):
    path = tmp_path / "app.log"
    path.write_text("")

    async def run():
        got = []
        async def reader():
            async for line in tail(str(path), poll=0.02):
                got.append(line)
        task = asyncio.create_task(reader())
        await asyncio.sleep(0.1)
        with open(path, "a") as f:
            f.write("one\ntwo\n")
        await asyncio.sleep(0.1)
        os.replace(path, str(path) + ".1")                 # rotate
        with open(path, "a") as f:
            f.write("three\n")
        await asyncio.sleep(0.2)
        task.cancel()
        return got

    assert asyncio.run(run()) == ["one", "two", "three"]
