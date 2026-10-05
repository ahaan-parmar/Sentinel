import { mockRequest } from './mock.js';

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
export const MOCK = new URLSearchParams(location.search).get('mock') === '1';

async function request(path, opts = {}) {
  if (MOCK) return mockRequest(path, opts);
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status} ${path}`);
  return res.json();
}

const post = (path, body) => request(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined });

export const api = {
  chat: (mode, message, day) => post('/chat', { mode, message, day }),
  ingest: (payload) => post('/ingest', payload),
  memories: () => request('/memories'),
  graph: () => request('/graph'),
  queue: () => request('/review-queue'),
  verify: () => request('/verify'),
  report: () => request('/report'),
  act: (verb, id) => post(id ? `/${verb}/${id}` : `/${verb}`),
};
