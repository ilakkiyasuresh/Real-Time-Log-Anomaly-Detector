import { useState, useEffect } from "react";
import { Play, Pause } from "lucide-react";

const fmt = (ts) =>
  new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

export default function LogTail({ logs }) {
  const [paused, setPaused] = useState(false);
  const [pausedLogs, setPausedLogs] = useState([]);
  const [freezeTime, setFreezeTime] = useState(null);
  const [search, setSearch] = useState("");
  const [levels, setLevels] = useState({ INFO: true, WARN: true, ERROR: true });

  useEffect(() => {
    if (paused && !freezeTime) {
      setFreezeTime(logs[0]?.ts);
      setPausedLogs(logs);
    } else if (!paused) {
      setFreezeTime(null);
    }
  }, [paused, logs, freezeTime]);

  const toggleLevel = (lvl) => setLevels(prev => ({ ...prev, [lvl]: !prev[lvl] }));

  const currentLogs = paused ? pausedLogs : logs;
  const newLines = paused && freezeTime ? logs.filter(l => l.ts > freezeTime).length : 0;

  const filtered = currentLogs.filter(l => {
    if (!levels[l.level]) return false;
    if (search && !l.msg.toLowerCase().includes(search.toLowerCase()) && !l.service.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  }).slice(0, 200);

  const highlight = (text) => {
    if (!search) return text;
    const parts = text.split(new RegExp(`(${search})`, 'gi'));
    return parts.map((part, i) => 
      part.toLowerCase() === search.toLowerCase() ? <mark key={i} style={{background: 'var(--violet)', color: '#fff', borderRadius: 2, padding: '0 2px'}}>{part}</mark> : part
    );
  };

  return (
    <div className="logtail-container">
      <div className="logtail-toolbar">
         <button onClick={() => setPaused(!paused)} className="pause-btn secondary">
            {paused ? <Play size={14} /> : <Pause size={14} />}
            {paused ? "Resume" : "Pause"}
         </button>
         
         {paused && newLines > 0 && (
           <div className="new-lines-badge">
             {newLines} new lines 
             <button className="jump-btn" onClick={() => setPaused(false)}>Jump to live</button>
           </div>
         )}
         
         <div className="log-levels">
            {["INFO", "WARN", "ERROR"].map(lvl => (
               <button key={lvl} className={`lvl-chip ${levels[lvl] ? 'active' : ''}`} onClick={() => toggleLevel(lvl)}>{lvl}</button>
            ))}
         </div>
         
         <input type="text" placeholder="Search logs..." value={search} onChange={e => setSearch(e.target.value)} className="log-search" />
      </div>
      
      <ol className="logtail">
        {filtered.length ? filtered.map((l, i) => (
          <li key={`${l.ts}-${i}`} className={`log-row log-${l.level.toLowerCase()}`}>
            <span className="log-time">{fmt(l.ts)}</span>
            <span className={`log-badge badge-${l.level.toLowerCase()}`}>{l.level}</span>
            <span className="log-svc"><span className={`svc-dot svc-${l.service}`} />{l.service}</span>
            <span className="log-msg">{highlight(l.msg)}</span>
          </li>
        )) : <div className="empty">No matching logs.</div>}
      </ol>
    </div>
  );
}
