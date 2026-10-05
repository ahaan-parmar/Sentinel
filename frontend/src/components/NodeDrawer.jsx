export default function NodeDrawer({ node, memory, onAction }) {
  if (!node) return <div className="drawer"><p className="muted">Select a node.</p></div>;
  const content = memory?.content ?? node.label;
  const hash = memory?.hash ?? '—';
  return (
    <div className="drawer">
      <h3 className="label">{node.type} · {node.id}</h3>
      <pre className="raw">{content}</pre>
      <dl className="dl">
        <dt>hash</dt><dd className="mono wrap">{hash}</dd>
        <dt>trust tier</dt><dd className="mono">{node.trust_tier}</dd>
        <dt>blame score</dt><dd className="mono">{Number(node.blame ?? 0).toFixed(2)}</dd>
        <dt>status</dt><dd className="mono">{node.status}</dd>
      </dl>
      <div className="row">
        <button className="btn" onClick={() => onAction('quarantine', node.id)}>Quarantine</button>
        <button className="btn" onClick={() => onAction('release', node.id)}>Release</button>
      </div>
    </div>
  );
}
