import { useState } from 'react';

export default function ReportModal({ report, onClose }) {
  const [copied, setCopied] = useState(false);
  const entries = Object.entries(report);
  const copy = async () => {
    await navigator.clipboard.writeText(entries.map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join('\n'));
    setCopied(true);
  };
  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2 className="label">INCIDENT REPORT</h2>
        <dl className="dl">
          {entries.map(([k, v]) => (
            <div key={k} className="dl-row">
              <dt>{k}</dt>
              <dd className="mono wrap">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</dd>
            </div>
          ))}
        </dl>
        <div className="row">
          <button className="btn" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
          <button className="btn" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
