# Sentinel

Git blame and git revert for AI agent memory. An external (tier-2) source plants a
poisoned "fact" in the agent's memory; Sentinel catches the agent trying to *act* on
it later, traces the blame back to that memory, and lets you quarantine or roll it back.

## Run it

```
pip install -r requirements.txt && python scripts/demo_seed.py
make backend
```

In a second terminal:

```
cd frontend && npm install && npm run dev
```

Open the printed Vite URL (default `http://localhost:5173`). Send "please send my
invoice" on Day 5: the plain agent executes and leaks to `attacker@evil.com`; the
Sentinel agent pauses for approval and the forensics graph lights up the poisoned
memory with blame score 1.0. Quarantine it from the graph to see it grey out.

`make demo` reseeds, `make test` runs the pytest suite, `bench/run.py` prints attack
success / false-block rates with and without Sentinel.

## Architecture

- `sentinel/models.py` — shared pydantic contracts every module imports from.
- `sentinel/ledger.py` — append-only, hash-chained sqlite store; tamper detection via `verify_chain`.
- `sentinel/trust.py` — pure lineage/trust-tier logic (derived tier = min of parents, quarantine cascades to descendants).
- `sentinel/gate.py` — write-time policy: blocks tier-2 writes unless they're plain facts; blocked writes go to a review queue.
- `sentinel/memory.py` — facade over the ledger; wraps tier-2 content in `<untrusted_data>` for retrieval.
- `sentinel/taint.py` — use-time check: does a risky tool call's target trace back to untrusted memory content?
- `sentinel/tools.py` — simulated tools (`read_email`/`send_email`/`http_request`); risky calls pause for approval when tainted.
- `sentinel/llm.py` / `sentinel/replay.py` — scripted or real Anthropic planner, plus counterfactual blame scoring.
- `sentinel/agent.py` + `sentinel/api.py` — the chat loop and the FastAPI routes wiring it together.
- `frontend/` — Vite + React UI: chat panes (plain vs Sentinel), forensics graph, ledger, review queue.

## Limits

- No real semantic search: `memory.search` is keyword-overlap matching, not embeddings.
- `SENTINEL_LLM_BACKEND` defaults to `scripted` (offline, deterministic); set `anthropic` + `ANTHROPIC_API_KEY` for a real model.
- Tools are simulated — no real network/email IO.
- `/graph` and `/report` reconstruct from an in-memory action history on the running process; it resets on restart or `/reset`.
- `/reset` wipes and reseeds the demo's sqlite files; it's an environment reset, not a ledger row delete (rows are never deleted).
- Frontend has a `?mock=1` offline fallback with its own canned dataset, independent of the real API.

![Sentinel UI](docs/screenshot.png)
