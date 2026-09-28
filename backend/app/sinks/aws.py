"""AWS sinks: CloudWatch Logs (every alert event), SNS (CRITICAL only), CloudWatch metrics.

Runs in the background on its own queue so a slow or failing AWS call never
blocks detection. If AWS is not configured (AWS_ENABLED != "1"), it runs in
mock mode: prints what it would send and still reports success to the UI,
so the whole team can develop without AWS credentials.
"""
import asyncio
import json
import os
import time


class AwsSink:
    def __init__(self, on_pushed=None):
        self.enabled = os.getenv("AWS_ENABLED", "0") == "1"
        self.region = os.getenv("AWS_REGION", "ap-south-1")
        self.log_group = os.getenv("CW_LOG_GROUP", "/hackathon/log-anomaly-detector")
        self.log_stream = os.getenv("CW_LOG_STREAM", "alerts")
        self.topic_arn = os.getenv("SNS_TOPIC_ARN", "")
        self.namespace = os.getenv("CW_METRIC_NAMESPACE", "LogAnomalyDetector")
        self.on_pushed = on_pushed            # async fn(alert_id, {"cloudwatch": bool, "sns": bool})
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._metric_buf: list = []
        if self.enabled:
            import boto3
            self.logs = boto3.client("logs", region_name=self.region)
            self.sns = boto3.client("sns", region_name=self.region)
            self.cw = boto3.client("cloudwatch", region_name=self.region)
            self._ensure_log_stream()

    # ---- setup ---------------------------------------------------------------
    def _ensure_log_stream(self):
        for call, kwargs in (
            (self.logs.create_log_group, {"logGroupName": self.log_group}),
            (self.logs.create_log_stream, {"logGroupName": self.log_group, "logStreamName": self.log_stream}),
        ):
            try:
                call(**kwargs)
            except self.logs.exceptions.ResourceAlreadyExistsException:
                pass

    # ---- pipeline listener ------------------------------------------------------
    async def handle(self, msg: dict):
        """Registered with pipeline.add_listener(). Never blocks: just enqueues."""
        if msg["type"] == "alert" and msg["event"] in ("new", "escalated", "resolved"):
            self._put(("alert", msg["event"], msg["data"]))
        elif msg["type"] == "metric":
            self._put(("metric", None, msg["data"]))

    def _put(self, item):
        if self.queue.full():
            self.queue.get_nowait()           # drop oldest rather than grow without limit
        self.queue.put_nowait(item)

    async def run(self):
        while True:
            kind, event, data = await self.queue.get()
            for attempt in range(3):
                try:
                    if kind == "alert":
                        await self._send_alert(event, data)
                    else:
                        await self._send_metric(data)
                    break
                except Exception as e:        # network blip, throttling, bad credentials...
                    print(f"[aws] {kind} send failed (attempt {attempt + 1}/3): {e!r}")
                    await asyncio.sleep(2 ** attempt)

    # ---- senders ---------------------------------------------------------------
    async def _send_alert(self, event: str, alert: dict):
        record = {"event": event, **{k: alert[k] for k in (
            "id", "severity", "status", "title", "reason", "service", "first_seen", "last_seen", "count", "evidence")}}
        pushed = {"cloudwatch": False, "sns": False}

        if self.enabled:
            await asyncio.to_thread(
                self.logs.put_log_events,
                logGroupName=self.log_group, logStreamName=self.log_stream,
                logEvents=[{"timestamp": int(time.time() * 1000), "message": json.dumps(record)}],
            )
        else:
            print(f"[aws:mock] CloudWatch Logs <- {json.dumps(record)[:160]}")
        pushed["cloudwatch"] = True

        # Page humans only for CRITICAL (new or escalated), and tell them when it recovers.
        if alert["severity"] == "CRITICAL":
            verb = {"new": "NEW", "escalated": "ESCALATED", "resolved": "RESOLVED"}[event]
            subject = f"[{verb}] {alert['severity']} {alert['title']}"[:99]   # SNS: under 100 chars, no line breaks
            body = (f"{alert['reason']}\n\nService: {alert['service']}\nOccurrences: {alert['count']}\n"
                    f"Alert id: {alert['id']}\n\nEvidence:\n" + "\n".join(alert["evidence"][-3:]))
            if self.enabled and self.topic_arn:
                await asyncio.to_thread(self.sns.publish, TopicArn=self.topic_arn, Subject=subject, Message=body)
                pushed["sns"] = True
            elif not self.enabled:
                print(f"[aws:mock] SNS <- {subject}")
                pushed["sns"] = True

        if self.on_pushed:
            await self.on_pushed(alert["id"], pushed)

    async def _send_metric(self, m: dict):
        """Custom metrics, batched: one PutMetricData call per 4 ticks."""
        ts = m["ts"]
        self._metric_buf += [
            {"MetricName": "ErrorRate", "Value": m["error_rate"] * 100, "Unit": "Percent", "Timestamp": ts},
            {"MetricName": "LinesPerWindow", "Value": m["total"], "Unit": "Count", "Timestamp": ts},
            {"MetricName": "AnomalyActive", "Value": 1 if m["anomalous"] else 0, "Unit": "Count", "Timestamp": ts},
        ]
        if len(self._metric_buf) < 12:
            return
        batch, self._metric_buf = self._metric_buf, []
        if self.enabled:
            await asyncio.to_thread(self.cw.put_metric_data, Namespace=self.namespace, MetricData=batch)
