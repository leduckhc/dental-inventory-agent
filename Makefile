.PHONY: help install run run-debug test test-verbose migrate requirements vllm lint format pre-commit pre-commit-install audit clean

# Default target
help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "  install          Install dependencies (uv sync)"
	@echo "  run              Run the agent (migrates DB on first run)"
	@echo "  run-debug        Run with debug output (tool calls + results)"
	@echo "  test             Run test suite (no LLM required)"
	@echo "  test-verbose     Run tests with verbose output"
	@echo "  migrate          Re-run inventory migration from case/inventory.json"
	@echo "  requirements     Regenerate requirements.txt from uv lockfile"
	@echo "  vllm             Start vLLM server (Qwen/Qwen3.5-9B on port 9000)"
	@echo "  lint             Run ruff check (type annotations, imports, style)"
	@echo "  format           Run ruff format"
	@echo "  pre-commit       Run all pre-commit hooks on every tracked file"
	@echo "  pre-commit-install  Install git hooks (run once after clone / make install)"
	@echo "  audit            Scan dependencies for known CVEs (pip-audit)"
	@echo "  clean            Remove generated DB and Python cache files"

install:
	uv sync

run:
	uv run python main.py

run-debug:
	uv run python main.py --debug

test:
	uv run pytest

test-verbose:
	uv run pytest -v

migrate:
	uv run python -m app.db.migrate

requirements:
	uv run export-requirements

lint:
	uv run ruff check app/ main.py scripts.py tests/

format:
	uv run ruff format app/ main.py scripts.py tests/

pre-commit:
	uv run pre-commit run --all-files

pre-commit-install:
	uv run pre-commit install

audit:
	uv run pip-audit --skip-editable

vllm:
	@set -a; [ -f .env ] && . ./.env; set +a; \
	CUDA_VISIBLE_DEVICES=1 vllm serve "Qwen/Qwen3.5-9B" \
		--enable-auto-tool-choice \
		--tool-call-parser qwen3_coder \
		--reasoning-parser qwen3 \
		--port 9000 \
		$${VLLM_API_KEY:+--api-key $${VLLM_API_KEY}}

clean:
	rm -f dental.db
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
