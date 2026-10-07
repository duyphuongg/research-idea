.PHONY: install migrate dev-backend dev-frontend test smoke rescore

install:
	cd backend && uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -e ".[dev]"
	cd backend && .venv/bin/python -m playwright install chromium
	cd frontend && npm install

migrate:
	cd backend && .venv/bin/alembic upgrade head

dev-backend:
	cd backend && .venv/bin/uvicorn --factory app.main:create_app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/pytest -q

smoke:
	cd backend && .venv/bin/python scripts/smoke.py

rescore:
	cd backend && .venv/bin/python scripts/rescore.py
