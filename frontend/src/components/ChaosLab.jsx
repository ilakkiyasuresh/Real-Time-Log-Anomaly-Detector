import { useState, useEffect } from "react";
import { Zap, TrendingUp, Bug, VolumeX, Activity, Timer } from "lucide-react";

const SCENARIOS = [
  { id: "error_burst", icon: Zap, color: "var(--violet)", name: "error_burst", desc: "Service suddenly fails 40% of requests" },
  { id: "error_creep", icon: TrendingUp, color: "var(--pink)", name: "error_creep", desc: "Errors rise slowly" },
  { id: "new_exception", icon: Bug, color: "var(--cyan)", name: "new_exception", desc: "A never-seen error appears" },
  { id: "silence", icon: VolumeX, color: "var(--violet)", name: "silence", desc: "Service stops logging" },
  { id: "traffic_spike", icon: Activity, color: "var(--pink)", name: "traffic_spike", desc: "Log volume jumps 5x" },
  { id: "latency", icon: Timer, color: "var(--cyan)", name: "latency", desc: "Many slow-response warnings" },
];

const SERVICES = ["auth", "gateway", "orders", "payments"];

export default function ChaosLab({ onInject, injections, alerts }) {
  const [scenario, setScenario] = useState("error_burst");
  const [service, setService] = useState("payments");
  const [duration, setDuration] = useState(30);
  const [loading, setLoading] = useState(false);
  const [now, setNow] = useState(Date.now() / 1000);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(timer);
  }, []);

  const isTrafficSpike = scenario === "traffic_spike";

  const inject = async () => {
    setLoading(true);
    const targetService = isTrafficSpike ? "*" : service;
    try {
      const r = await fetch(`/api/inject?scenario=${scenario}&service=${targetService}&duration=${duration}`, { method: "POST" });
      if (r.ok) {
        onInject({ scenario, service: targetService, startedAt: Date.now() / 1000, duration });
      }
    } finally {
      setLoading(false);
    }
  };

  const results = injections.map(inj => {
    const matchedAlert = alerts.find(a => 
      (a.service === inj.service || a.service === '*') && 
      a.first_seen >= inj.startedAt && 
      a.first_seen <= inj.startedAt + inj.duration + 30
    );
    
    let status = "";
    let time = null;
    
    if (matchedAlert) {
      time = matchedAlert.first_seen - inj.startedAt;
      status = time <= 10 ? "fast" : "slow";
    } else {
      const elapsed = now - inj.startedAt;
      if (elapsed > inj.duration + 30) {
        status = "missed";
      } else {
        status = "waiting";
      }
    }
    return { ...inj, matchedAlert, time, status };
  }).reverse();

  const detected = results.filter(r => r.time !== null);
  const avgTime = detected.length ? (detected.reduce((sum, r) => sum + r.time, 0) / detected.length).toFixed(1) : null;

  return (
    <div className="chaos-lab">
      <h3>Chaos Lab</h3>
      <div className="scenario-grid">
         {SCENARIOS.map(s => {
           const Icon = s.icon;
           return (
             <div key={s.id} className={`scenario-card ${scenario === s.id ? 'active' : ''}`} onClick={() => setScenario(s.id)}>
               <div className="scenario-icon" style={{ backgroundColor: s.color }}>
                 <Icon size={20} color="#fff" />
               </div>
               <div className="scenario-info">
                 <div className="scenario-name">{s.name}</div>
                 <div className="scenario-desc">{s.desc}</div>
               </div>
             </div>
           );
         })}
      </div>
      
      <div className="chaos-controls">
         <div className="service-chips">
           {SERVICES.map(svc => (
             <button 
               key={svc} 
               className={`svc-chip ${service === svc ? 'active' : ''}`} 
               disabled={isTrafficSpike}
               onClick={() => setService(svc)}
             >
               <span className={`svc-dot svc-${svc}`} />
               {svc}
             </button>
           ))}
         </div>
         
         <div className="duration-slider">
           <label>Duration: {duration}s</label>
           <input type="range" min="10" max="60" step="10" value={duration} onChange={e => setDuration(Number(e.target.value))} />
         </div>
         
         <button className="primary inject-btn" onClick={inject} disabled={loading}>
           {loading ? "Injecting..." : "Inject anomaly"}
         </button>
      </div>

      {results.length > 0 && (
         <div className="detection-results">
            <div className="detection-header">
               <h4>Detection results</h4>
               {avgTime && <span className="avg-pill">Avg detection: {avgTime}s</span>}
            </div>
            <ul className="detection-list">
               {results.map((r, i) => (
                  <li key={i}>
                     <span className="det-scen">{r.scenario}</span> on <span className="det-svc">{r.service}</span> — 
                     {r.status === "fast" && <span className="det-fast"> Detected in {r.time.toFixed(1)} s</span>}
                     {r.status === "slow" && <span className="det-slow"> Detected in {r.time.toFixed(1)} s</span>}
                     {r.status === "waiting" && <span className="det-wait"> Waiting...</span>}
                     {r.status === "missed" && <span className="det-miss"> Not detected</span>}
                  </li>
               ))}
            </ul>
         </div>
      )}
    </div>
  );
}
