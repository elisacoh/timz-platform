.PHONY: run lint fmt test

run:
	uvicorn app.main:app --reload

lint:
	flake8
	isort . --check
	black --check .

fmt:
	isort .
	black .

test:
	pytest -q
