.PHONY: help install install-dev format lint typecheck test check clean

help:  ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install package with UV
	uv pip install -e .

install-dev:  ## Install package with dev dependencies
	uv pip install -e ".[dev]"

format:  ## Format code with ruff
	ruff format .
	ruff check --fix .

lint:  ## Lint code with ruff
	ruff check .

typecheck:  ## Type check with mypy (strict mode)
	mypy auto_improvement

test:  ## Run tests with pytest
	pytest tests/ -v --cov=auto_improvement --cov-report=term-missing

check: lint typecheck  ## Run all checks (lint + typecheck)

clean:  ## Clean up cache files
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .coverage htmlcov/

all: format check  ## Format and check everything
