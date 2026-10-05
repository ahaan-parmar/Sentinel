export default function Ledger({ memories }) {
  return (
    <section>
      <h2 className="label">MEMORY LEDGER</h2>
      <table className="ledger">
        <thead>
          <tr><th>id</th><th>source</th><th>tier</th><th>kind</th><th>status</th><th>hash</th></tr>
        </thead>
        <tbody>
          {memories.map((m) => (
            <tr key={m.id} className={`${m.trust_tier === 2 ? 'tier2' : ''} ${m.status === 'quarantined' ? 'quarantined' : ''}`}>
              <td>{m.id}</td><td title={m.source}>{m.source}</td><td>{m.trust_tier}</td>
              <td>{m.kind}</td><td>{m.status}</td><td>{(m.hash || '').slice(0, 8)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {memories.length === 0 && <p className="muted">Ledger empty.</p>}
    </section>
  );
}
