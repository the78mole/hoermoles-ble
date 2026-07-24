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
SITE_DIR     := _site
PREVIEW_DIR  := .preview
# First segment of HOERMOLES_BASE, i.e. the GitHub Pages project name - used to
# serve the preview under the same prefix the deployed site uses.
PAGES_PREFIX  = $(word 1,$(subst /, ,$(HOERMOLES_BASE)))
NODE_MODULES := $(SPA_DIR)/node_modules
VENV         := $(PYTHON_DIR)/.venv

# Must match where the app is actually served from. On GitHub Pages that is
# /<repo>/app/ - the app sits in a subdirectory so the site root stays free for
# other content (see pages/ and the "Assemble the site" step in spa-deploy.yml).
# `make build` passes it explicitly so a local build matches the deployed one;
# override it when hosting the app at a domain root: `make build HOERMOLES_BASE=/`
HOERMOLES_BASE ?= /hoermoles-ble/app/

.DEFAULT_GOAL := help

.PHONY: help dev build site test test-python test-spa install lint format \
        typecheck shared icons preview clean

help:  ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- the three the README promises -----------------------------------------

dev: $(NODE_MODULES)  ## Start the web app dev server (http://localhost:5173/hoermoles-ble/app/)
	@echo "Web Bluetooth needs Chrome or Edge. On Linux also enable"
	@echo "chrome://flags/#enable-experimental-web-platform-features"
	cd $(SPA_DIR) && npm run dev

build: site  ## Build the static site exactly as GitHub Pages receives it

site: $(NODE_MODULES)  ## Assemble _site/ (landing page + app under app/), like the deploy does
	cd $(SPA_DIR) && HOERMOLES_BASE=$(HOERMOLES_BASE) npm run build
	rm -rf $(SITE_DIR)
	mkdir -p $(SITE_DIR)
	cp -r pages/. $(SITE_DIR)/
	cp -r $(DIST_DIR) $(SITE_DIR)/app
	@echo
	@echo "Site assembled in $(SITE_DIR)/ - app at $(SITE_DIR)/app (base $(HOERMOLES_BASE))."
	@echo "Serve it with 'make preview'; opening index.html via file:// will not work,"
	@echo "since the app needs a secure context and absolute base paths."

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

preview: site  ## Assemble the site, then serve it at the real production paths
	# The build hardcodes absolute paths under $(HOERMOLES_BASE), so serving
	# _site/ directly would 404 on every asset. Symlinking it under the same
	# first path segment GitHub Pages uses reproduces the deployed URLs exactly,
	# which is the whole point of previewing rather than just running `dev`.
	rm -rf $(PREVIEW_DIR)
	mkdir -p $(PREVIEW_DIR)
	ln -sfn $(CURDIR)/$(SITE_DIR) $(PREVIEW_DIR)/$(PAGES_PREFIX)
	@echo
	@echo "Landing page: http://localhost:4173/$(PAGES_PREFIX)/"
	@echo "Web app:      http://localhost:4173$(HOERMOLES_BASE)"
	@echo
	cd $(PREVIEW_DIR) && python3 -m http.server 4173 --bind 127.0.0.1

install: $(VENV) $(NODE_MODULES)  ## Install all dependencies

clean:  ## Remove build output and coverage reports
	rm -rf $(DIST_DIR) $(SITE_DIR) $(PREVIEW_DIR) $(SPA_DIR)/packages/webapp/dev-dist $(SPA_DIR)/coverage
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
