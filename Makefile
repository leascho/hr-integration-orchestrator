.PHONY: install lint format format-check test coverage check run up down logs reset demo-success demo-invalid

PYTHON ?= python
BASE_URL ?= http://localhost:8000
MOCK_URL ?= http://localhost:8100

install:
	$(PYTHON) -m pip install -e ".[dev]"

lint:
	ruff check .

format:
	ruff format .
	ruff check --fix .

format-check:
	ruff format --check .

test:
	pytest

coverage:
	pytest --cov=app --cov-report=term-missing --cov-report=xml

check: lint format-check test

run:
	uvicorn app.asgi:app --reload --port 8000

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f orchestrator

reset:
	docker compose down -v

demo-success:
	curl -s -X POST $(BASE_URL)/api/v1/events/employee-created \
	  -H "Content-Type: application/json" -H "X-Correlation-ID: demo-success-001" \
	  -d @examples/employee-created.json

demo-invalid:
	curl -s -X POST $(BASE_URL)/api/v1/events/employee-created \
	  -H "Content-Type: application/json" \
	  -d @examples/employee-created-invalid.json

