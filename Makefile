.PHONY: format-check lint type-check unit-test frontend-test test db-upgrade db-downgrade

format-check:
	cd backend && python -m ruff format --check .

lint:
	cd backend && python -m ruff check .

type-check:
	cd backend && python -m mypy src tests
	cd frontend && npm run type-check

unit-test:
	cd backend && python -m pytest

frontend-test:
	cd frontend && npm run test -- --run

test: unit-test frontend-test

db-upgrade:
	cd backend && python -m alembic upgrade head

db-downgrade:
	cd backend && python -m alembic downgrade base
