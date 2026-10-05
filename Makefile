.PHONY: backend frontend demo test

backend:
	PYTHONPATH=. SENTINEL_LLM_BACKEND=scripted python -m uvicorn sentinel.api:app --reload --port 8000

frontend:
	cd frontend && npm run dev

demo:
	PYTHONPATH=. SENTINEL_LLM_BACKEND=scripted python scripts/demo_seed.py

test:
	PYTHONPATH=. SENTINEL_LLM_BACKEND=scripted pytest tests/ -q
