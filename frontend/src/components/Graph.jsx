import { useEffect, useRef, useState } from 'react';
import NodeDrawer from './NodeDrawer.jsx';

const COLS = { source: 0, memory: 1, derived: 2, tool_call: 3 };
const W = 560, H = 380, PAD_X = 60, STEP_X = 146, STEP_Y = 78;

function layout(nodes) {
  const rows = {};
  return Object.fromEntries(nodes.map((n) => {
    const c = COLS[n.type] ?? 1;
    const r = (rows[c] = (rows[c] ?? -1) + 1);
    return [n.id, { x: PAD_X + c * STEP_X, y: 56 + r * STEP_Y }];
  }));
}

function fillClass(n) {
  if (n.status === 'quarantined') return 'n-rolled';
  if (n.blame) return 'n-alert';
  if (n.trust_tier === 2) return 'n-tier2';
  return 'n-clean';
}

function Shape({ type, cls, selected }) {
  const c = `shape ${cls}${selected ? ' selected' : ''}`;
  if (type === 'source') return <rect className={c} x="-11" y="-11" width="22" height="22" />;
  if (type === 'tool_call') return <polygon className={c} points="0,-15 15,0 0,15 -15,0" />;
  return <circle className={c} r={type === 'derived' ? 6 : 12} />;
}

export default function Graph({ graph, memories, onAction }) {
  const [selected, setSelected] = useState(null);
  const [day, setDay] = useState(5);
  const timer = useRef(null);
  const pos = layout(graph.nodes);
  const seen = (n) => (n.day ?? 1) <= day;
  const visible = graph.nodes.filter(seen);
  const ids = new Set(visible.map((n) => n.id));
  const node = graph.nodes.find((n) => n.id === selected);

  useEffect(() => () => clearInterval(timer.current), []);

  const replay = () => {
    clearInterval(timer.current);
    let d = 1;
    setDay(1);
    timer.current = setInterval(() => {
      d += 1; setDay(d);
      if (d >= 5) clearInterval(timer.current);
    }, 700);
  };

  return (
    <section className="col col-center">
      <h2 className="label">FORENSICS GRAPH</h2>
      <svg className="graph" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Provenance graph">
        {graph.edges.filter((e) => ids.has(e.from) && ids.has(e.to)).map((e) => {
          const a = pos[e.from], b = pos[e.to];
          return (
            <g key={`${e.from}-${e.to}`} className="edge appear">
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
              <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 5} textAnchor="middle">{e.type}</text>
            </g>
          );
        })}
        {visible.map((n) => (
          <g key={n.id} className="node appear" transform={`translate(${pos[n.id].x},${pos[n.id].y})`}
            onClick={() => setSelected(n.id)}>
            <Shape type={n.type} cls={fillClass(n)} selected={n.id === selected} />
            <text y="30" textAnchor="middle">{n.label.length > 22 ? n.label.slice(0, 21) + '…' : n.label}</text>
          </g>
        ))}
      </svg>
      <div className="slider">
        <span className="label">Day {day}</span>
        <input type="range" min="1" max="5" value={day} onChange={(e) => setDay(Number(e.target.value))} />
        <button className="link" onClick={replay}>Replay</button>
      </div>
      <NodeDrawer node={node} memory={memories.find((m) => m.id === selected)} onAction={onAction} />
      <div><button className="btn btn-alert" onClick={() => onAction('rollback')}>Rollback</button></div>
    </section>
  );
}
