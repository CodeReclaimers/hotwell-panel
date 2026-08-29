# Dev runs two processes (PLAN-panel.md §2): uvicorn for the sim/WebSocket,
# vite dev for the client with HMR proxying /ws. `make check` is the full
# §12 gate: client checks, python lint, then the pytest suite (browser tests
# need chromium and a built client/dist).

.PHONY: dev build check

dev:
	trap 'kill 0' EXIT; .venv/bin/python -m uvicorn --factory hotwell_panel.server:create_app --port 8000 & cd client && npm run dev

build:
	cd client && npm run build

check:
	cd client && npm run check && npm test
	.venv/bin/python -m ruff check .
	.venv/bin/python -m pytest
