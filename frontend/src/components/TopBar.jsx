export default function TopBar({ verify, mock, onVerify, onReset, onExport }) {
  const state = verify == null ? 'pending' : verify.ok ? 'safe' : 'alert';
  const text = verify == null ? 'chain: unknown' : verify.ok ? 'chain: verified' : `chain: broken at ${verify.broken_at}`;
  return (
    <header className="topbar">
      <h1 className="wordmark">SENTINEL</h1>
      {mock && <span className="label">mock data</span>}
      <span className={`status status-${state}`}>{text}</span>
      <button className="btn" onClick={onVerify}>Verify</button>
      <span className="spacer" />
      <button className="btn" onClick={onReset}>Reset</button>
      <button className="btn" onClick={onExport}>Export report</button>
    </header>
  );
}
