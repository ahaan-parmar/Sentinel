import ActionRow from './ActionRow.jsx';

export default function ChatPane({ title, entries, busy, onResolve }) {
  return (
    <section className="pane">
      <h2 className="label">{title}</h2>
      <div className="pane-log">
        {entries.length === 0 && <p className="muted">No messages.</p>}
        {entries.map((e, i) => (
          <div key={i} className="entry">
            <p className="entry-user"><span className="label">day {e.day} ›</span> {e.message}</p>
            {e.error ? <p className="text-alert">{e.error}</p> : e.pending ? <p className="muted">…</p> : (
              <>
                <p className="entry-reply">{e.reply}</p>
                {e.actions.map((a, j) => (
                  <ActionRow key={j} action={a}
                    onApprove={() => onResolve(i, j, 'approve')}
                    onDeny={() => onResolve(i, j, 'deny')} />
                ))}
              </>
            )}
          </div>
        ))}
      </div>
      {busy && <span className="label">waiting</span>}
    </section>
  );
}
