.PHONY: setup venv install format clean help

VENV = .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip

default: help

setup: venv install ## Setup virtual environment and install dependencies

venv: ## Create virtual environment
	python3 -m venv $(VENV)

install: venv ## Install dependencies from requirements.txt
	$(PIP) install -r requirements.txt

format: ## Format source code using black
	$(PYTHON) -m black .

clean: ## Remove virtual environment and cache files
	rm -rf $(VENV)
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
