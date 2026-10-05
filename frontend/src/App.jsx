import { useCallback, useEffect, useState } from 'react';
import { api, MOCK } from './api.js';
import TopBar from './components/TopBar.jsx';
import ChatPanes from './components/ChatPanes.jsx';
import Graph from './components/Graph.jsx';
import Ledger from './components/Ledger.jsx';
import ReviewQueue from './components/ReviewQueue.jsx';
import ReportModal from './components/ReportModal.jsx';

const EMPTY = { sentinel: [] };

export default function App() {
  const [memories, setMemories] = useState([]);
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [queue, setQueue] = useState([]);
  const [verify, setVerify] = useState(null);
  const [report, setReport] = useState(null);
  const [chat, setChat] = useState(EMPTY);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    try {
      const [m, g, q, v] = await Promise.all([api.memories(), api.graph(), api.queue(), api.verify()]);
      setMemories(m); setGraph(g); setQueue(q); setVerify(v); setError('');
    } catch (e) { setError(`API unreachable: ${e.message}. Use ?mock=1 for demo data.`); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const run = async (fn) => { try { await fn(); await refresh(); } catch (e) { setError(e.message); } };
  const act = (verb, id) => run(() => api.act(verb, id));

  const reset = () => run(async () => { await api.act('reset'); setChat(EMPTY); });
  const exportReport = async () => { try { setReport(await api.report()); } catch (e) { setError(e.message); } };

  return (
    <div className="app">
      <TopBar verify={verify} mock={MOCK} onVerify={refresh} onReset={reset} onExport={exportReport} />
      {error && <div className="banner">{error}</div>}
      <main className="columns">
        <ChatPanes chat={chat} setChat={setChat} onChanged={refresh} />
        <Graph graph={graph} memories={memories} onAction={act} />
        <aside className="col col-right">
          <Ledger memories={memories} />
          <ReviewQueue items={queue} />
        </aside>
      </main>
      {report && <ReportModal report={report} onClose={() => setReport(null)} />}
    </div>
  );
}
