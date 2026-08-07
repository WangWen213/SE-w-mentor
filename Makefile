BACKEND_PYTHON ?= ./.venv/Scripts/python.exe
REPO_PYTHON ?= ./backend/.venv/Scripts/python.exe
NPM ?= npm.cmd

.PHONY: format-check lint type-check unit-test frontend-test test db-upgrade db-downgrade check-all

format-check:
	cd backend && $(BACKEND_PYTHON) -m ruff format --check .

lint:
	cd backend && $(BACKEND_PYTHON) -m ruff check .

type-check:
	cd backend && $(BACKEND_PYTHON) -m mypy src tests
	cd frontend && $(NPM) run type-check

unit-test:
	cd backend && $(BACKEND_PYTHON) -m pytest

frontend-test:
	cd frontend && $(NPM) run test -- --run

test: unit-test frontend-test

check-all:
	$(REPO_PYTHON) scripts/check_all.py

db-upgrade:
	cd backend && $(BACKEND_PYTHON) -m alembic upgrade head

db-downgrade:
	cd backend && $(BACKEND_PYTHON) -m alembic downgrade base
