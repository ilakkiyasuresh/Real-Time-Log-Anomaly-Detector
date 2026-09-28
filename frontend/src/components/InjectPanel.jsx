import { useState } from "react";

const SCENARIOS = ["error_burst", "error_creep", "new_exception", "silence", "traffic_spike", "latency"];
const SERVICES = ["payments", "orders", "auth", "gateway"];

export default function InjectPanel({ onInject }) {
  const [scenario, setScenario] = useState("error_burst");
  const [service, setService] = useState("payments");
  const [note, setNote] = useState("");

  const inject = async () => {
    setNote("Injecting…");
    try {
      const r = await fetch(`/api/inject?scenario=${scenario}&service=${service}&duration=30`, { method: "POST" });
      if (r.ok) {
        onInject({ scenario, service, startedAt: Date.now() / 1000, duration: 30 });
        setNote(`Injected ${scenario} on ${service} for 30 s`);
      } else {
        setNote("Generator not reachable");
      }
    } catch {
      setNote("Backend not reachable");
    }
    setTimeout(() => setNote(""), 4000);
  };

  return (
    <div className="inject">
      <select value={scenario} onChange={(e) => setScenario(e.target.value)} aria-label="Scenario">
        {SCENARIOS.map((s) => (
          <option key={s}>{s}</option>
        ))}
      </select>
      <select value={service} onChange={(e) => setService(e.target.value)} aria-label="Service">
        {SERVICES.map((s) => (
          <option key={s}>{s}</option>
        ))}
      </select>
      <button onClick={inject}>Inject anomaly</button>
      {note && <span className="muted">{note}</span>}
    </div>
  );
}
