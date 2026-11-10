.PHONY: install migrate dev test lint verify

install:
	python -m pip install -e '.[dev]'

migrate:
	alembic upgrade head

dev:
	uvicorn shipgate.api:app --host 127.0.0.1 --port 8000 --reload

test:
	pytest -q --cov=shipgate --cov-report=term-missing

lint:
	ruff check .

verify:
	python -m compileall -q shipgate alembic tests
	pytest -q
