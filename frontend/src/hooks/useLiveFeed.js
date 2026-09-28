import { useEffect, useRef, useState } from "react";

const MAX_LOGS = 200;
const MAX_METRICS = 120; // 10 minutes at a 5 s tick

function wsUrl() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws`;
}

// Insert or replace an alert by id, newest first.
function upsert(list, alert) {
  const i = list.findIndex((a) => a.id === alert.id);
  if (i === -1) return [alert, ...list].slice(0, 100);
  const copy = list.slice();
  const was = copy[i].pushed || {};
  const now = alert.pushed || {};
  // A tick, once earned, stays: OR the old and new pushed flags.
  copy[i] = { ...copy[i], ...alert, pushed: { cloudwatch: !!(was.cloudwatch || now.cloudwatch), sns: !!(was.sns || now.sns) } };
  return copy;
}

export function useLiveFeed() {
  const [status, setStatus] = useState("connecting");
  const [logs, setLogs] = useState([]);
  const [metrics, setMetrics] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [linesPerSec, setLinesPerSec] = useState(0);
  const counter = useRef([]); // [timestamp, n] pairs for lines/sec

  useEffect(() => {
    let ws;
    let retryTimer;
    let retryDelay = 1000;
    let closedByUs = false;

    const connect = () => {
      ws = new WebSocket(wsUrl());
      ws.onopen = () => {
        setStatus("live");
        retryDelay = 1000;
      };
      ws.onclose = () => {
        if (closedByUs) return;
        setStatus("reconnecting");
        retryTimer = setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 10000); // back off: 1s, 2s, 4s ... 10s
      };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        switch (msg.type) {
          case "snapshot":
            setLogs([...msg.data.logs].reverse().slice(0, MAX_LOGS));
            setMetrics(msg.data.metrics.slice(-MAX_METRICS));
            setAlerts(msg.data.alerts);
            break;
          case "log_batch": {
            setLogs((prev) => [...[...msg.data].reverse(), ...prev].slice(0, MAX_LOGS));
            const now = Date.now();
            counter.current = [...counter.current.filter(([t]) => now - t < 5000), [now, msg.data.length]];
            break;
          }
          case "metric":
            setMetrics((prev) => [...prev, msg.data].slice(-MAX_METRICS));
            break;
          case "alert":
            setAlerts((prev) => upsert(prev, msg.data));
            break;
          case "alert_pushed": {
            const { id, ...pushed } = msg.data;
            setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, pushed: { ...a.pushed, ...pushed } } : a)));
            break;
          }
          default:
            break;
        }
      };
    };

    connect();
    const rate = setInterval(() => {
      const now = Date.now();
      const recent = counter.current.filter(([t]) => now - t < 5000);
      setLinesPerSec(recent.reduce((s, [, n]) => s + n, 0) / 5);
    }, 1000);

    return () => {
      closedByUs = true;
      clearTimeout(retryTimer);
      clearInterval(rate);
      if (ws) ws.close();
    };
  }, []);

  return { status, logs, metrics, alerts, linesPerSec };
}
