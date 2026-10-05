const CLASS = { executed: 'alert', blocked: 'safe', pending_approval: 'pending' };

export default function ActionRow({ action, onApprove, onDeny }) {
  const status = (action.status || '').toLowerCase();
  const args = typeof action.args === 'string' ? action.args : Object.values(action.args || {}).join(', ');
  return (
    <div className="action-row">
      <span className="action-call">{action.tool} → {args}</span>
      <span className={`action-status text-${CLASS[status] || 'muted'}`}>{status.toUpperCase()}</span>
      {status === 'pending_approval' && (
        <span className="action-buttons">
          <button className="link" onClick={onApprove}>Approve</button>
          <button className="link" onClick={onDeny}>Deny</button>
        </span>
      )}
    </div>
  );
}
