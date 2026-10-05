export default function ReviewQueue({ items }) {
  return (
    <section>
      <h2 className="label">REVIEW QUEUE</h2>
      {items.length === 0 && <p className="muted">No blocked writes.</p>}
      <ul className="queue">
        {items.map((q) => (
          <li key={q.id}>
            <span className="mono">{q.id}</span>{q.source && <span className="mono muted"> · {q.source}</span>}
            <p>{q.reason}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
