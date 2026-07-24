# Convenience entry points for the whole monorepo. The underlying tools (uv,
# npm) remain the source of truth - these targets only spare you remembering
# which directory each one has to run in.
#
#   make dev     start the web app's dev server
#   make build   build the static site exactly as GitHub Pages gets it
#   make test    run every test suite: Python and TypeScript
#
# `make help` lists everything.

SHELL := /bin/bash

PYTHON_DIR   := python
SPA_DIR      := spa
DIST_DIR     := $(SPA_DIR)/packages/webapp/dist
NODE_MODULES := $(SPA_DIR)/node_modules
VENV         := $(PYTHON_DIR)/.venv

# Must match the GitHub Pages project-site path, i.e. /<repo>/. `make build`
# passes it explicitly so a local build is byte-comparable to the deployed one;
# override it when hosting at a domain root: `make build HOERMOLES_BASE=/`
HOERMOLES_BASE ?= /hoermoles-ble/

.DEFAULT_GOAL := help

.PHONY: help dev build test test-python test-spa install lint format typecheck \
        shared icons preview clean

help:  ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- the three the README promises -----------------------------------------

dev: $(NODE_MODULES)  ## Start the web app dev server (http://localhost:5173/hoermoles-ble/)
	@echo "Web Bluetooth needs Chrome or Edge. On Linux also enable"
	@echo "chrome://flags/#enable-experimental-web-platform-features"
	cd $(SPA_DIR) && npm run dev

build: $(NODE_MODULES)  ## Build the static site as GitHub Pages receives it
	cd $(SPA_DIR) && HOERMOLES_BASE=$(HOERMOLES_BASE) npm run build
	@echo
	@echo "Static site in $(DIST_DIR) (base $(HOERMOLES_BASE))."
	@echo "Serve it with 'make preview' - opening index.html via file:// will not"
	@echo "work, since the app needs a secure context and absolute base paths."

test: test-python test-spa  ## Run every test suite (Python + TypeScript)

# --- per-language --------------------------------------------------------

test-python: $(VENV)  ## Python tests only (pytest, with coverage gate)
	cd $(PYTHON_DIR) && uv run pytest --cov --cov-report=term-missing --cov-fail-under=80

test-spa: $(NODE_MODULES)  ## TypeScript tests only (vitest, with coverage gate)
	cd $(SPA_DIR) && npx vitest run --coverage

lint: $(VENV) $(NODE_MODULES)  ## Lint both halves without modifying anything
	cd $(PYTHON_DIR) && uv run ruff check packages scripts
	cd $(PYTHON_DIR) && uv run ruff format --check packages scripts
	cd $(SPA_DIR) && npx eslint .
	cd $(SPA_DIR) && npx prettier --check .

format: $(VENV) $(NODE_MODULES)  ## Auto-format both halves
	cd $(PYTHON_DIR) && uv run ruff check --fix packages scripts
	cd $(PYTHON_DIR) && uv run ruff format packages scripts
	cd $(SPA_DIR) && npx eslint . --fix
	cd $(SPA_DIR) && npx prettier --write .

typecheck: $(NODE_MODULES)  ## Typecheck the TypeScript and Svelte sources
	cd $(SPA_DIR) && npm run typecheck

# --- generated artifacts --------------------------------------------------

shared: $(VENV)  ## Regenerate shared/*.json from the Python implementation
	cd $(PYTHON_DIR) && uv run python scripts/generate_shared.py

icons: ## Regenerate the app icons from shared/assets (needs Pillow)
	cd $(SPA_DIR) && python3 scripts/generate-icons.py

# --- misc -----------------------------------------------------------------

preview: build  ## Build, then serve the production bundle locally
	cd $(SPA_DIR) && npm run preview

install: $(VENV) $(NODE_MODULES)  ## Install all dependencies

clean:  ## Remove build output and coverage reports
	rm -rf $(DIST_DIR) $(SPA_DIR)/packages/webapp/dev-dist $(SPA_DIR)/coverage
	rm -rf $(PYTHON_DIR)/.coverage $(PYTHON_DIR)/coverage.xml $(PYTHON_DIR)/coverage.json

# --- dependency guards ----------------------------------------------------
# Ordinary prerequisites, so a fresh clone can run any target directly instead
# of failing on a missing venv or node_modules.

$(NODE_MODULES): $(SPA_DIR)/package-lock.json
	cd $(SPA_DIR) && npm ci
	@touch $@

$(VENV): $(PYTHON_DIR)/uv.lock $(PYTHON_DIR)/pyproject.toml
	cd $(PYTHON_DIR) && uv sync --all-packages
	@touch $@
