"""End-to-end check: run the pipeline against the live generator and print alerts.

Start the generator first:  python generator/log_generator.py --rate 30
Then:                       python backend/e2e_check.py
"""
import asyncio
import json
import time
import urllib.request

from app.pipeline import Pipeline

GEN = "http://localhost:8099"
SCHEDULE = [   # (seconds after start, scenario, service, duration)
    (40, "error_burst", "payments", 20),
    (75, "new_exception", "orders", 15),
    (100, "traffic_spike", "gateway", 15),
    (130, "silence", "gateway", 20),
]
RUN_FOR = 165


def inject(scenario, service, duration):
    req = urllib.request.Request(f"{GEN}/inject?scenario={scenario}&service={service}&duration={duration}", method="POST")
    urllib.request.urlopen(req).read()


async def main():
    p = Pipeline("../generator/logs/app.log", window_s=20, tick_s=2, warmup_ticks=10)
    start = time.time()

    async def printer(msg):
        t = time.time() - start
        if msg["type"] == "alert":
            a = msg["data"]
            print(f"t={t:5.1f}s  {msg['event']:<9} {a['severity']:<8} {a['fingerprint']:<40} {a['reason']}")
        elif msg["type"] == "metric" and int(t) % 10 < 2:
            m = msg["data"]
            print(f"t={t:5.1f}s  metric    rate={m['error_rate']:.3f} base={m['baseline_mean'] or 0:.3f} "
                  f"total={m['total']} ready={m['baseline_ready']}")

    p.add_listener(printer)
    tasks = [asyncio.create_task(c) for c in p.tasks()]

    async def scheduler():
        for at, sc, svc, dur in SCHEDULE:
            await asyncio.sleep(max(0, start + at - time.time()))
            print(f"t={time.time()-start:5.1f}s  >>> INJECT {sc} on {svc} for {dur}s")
            inject(sc, svc, dur)
    tasks.append(asyncio.create_task(scheduler()))
    await asyncio.sleep(RUN_FOR)
    for t in tasks:
        t.cancel()
    print(f"lines processed: {p.lines_total}, alerts: {len(p.alerts.history)}")


if __name__ == "__main__":
    asyncio.run(main())
