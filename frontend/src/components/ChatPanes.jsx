import { useState } from 'react';
import { api } from '../api.js';
import ChatPane from './ChatPane.jsx';

const NEXT = { approve: 'executed', deny: 'blocked' };

export default function ChatPanes({ chat, setChat, onChanged }) {
  const [text, setText] = useState('');
  const [day, setDay] = useState(1);

  const patch = (mode, fn) => setChat((c) => ({ ...c, [mode]: fn(c[mode]) }));

  const send = async (e) => {
    e.preventDefault();
    const message = text.trim();
    if (!message) return;
    setText('');
    const idx = chat.sentinel.length;
    patch('sentinel', (l) => [...l, { message, day, pending: true, actions: [] }]);
    api.chat('sentinel', message, day)
      .then((r) => patch('sentinel', (l) => l.map((x, i) => (i === idx ? { ...x, ...r, pending: false, actions: r.actions || [] } : x))))
      .catch((err) => patch('sentinel', (l) => l.map((x, i) => (i === idx ? { ...x, pending: false, error: err.message } : x))))
      .finally(onChanged);
  };

  const resolve = async (entry, j, verb) => {
    const a = chat.sentinel[entry].actions[j];
    await api.act(verb, a.action_id);
    patch('sentinel', (l) => l.map((x, i) => (i !== entry ? x
      : { ...x, actions: x.actions.map((y, k) => (k === j ? { ...y, status: NEXT[verb] } : y)) })));
    onChanged();
  };

  return (
    <section className="col col-left">
      <ChatPane title="SENTINEL" entries={chat.sentinel} onResolve={resolve} />
      <form className="composer" onSubmit={send}>
        <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Message Sentinel" />
        <select className="input select" value={day} onChange={(e) => setDay(Number(e.target.value))}>
          <option value={1}>Day 1</option>
          <option value={5}>Day 5</option>
        </select>
        <button className="btn" type="submit">Send</button>
      </form>
    </section>
  );
}
