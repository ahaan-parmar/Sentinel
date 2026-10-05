# Sentinel UI

Forensic view of how a poisoned agent memory led to a blocked attack. React + Vite + plain CSS. The graph is hand-drawn SVG, so there are no extra dependencies.

1. `npm install`
2. `npm run dev`
3. Open http://localhost:5173 — add `?mock=1` to run without the backend (API expected at http://localhost:8000 otherwise).

Optional contract notes: actions may carry an `id` (used for `/approve/{id}` and `/deny/{id}`); graph nodes may carry a `day` (1–5) for timeline replay.
