SHELL := /bin/sh
ORG_SCRIPTS_DIR ?= $(HOME)/.local/share/solierrr-infra-scripts
ORG_SCRIPTS_POWERSHELL ?= powershell
EXTRACT_ENV := $(ORG_SCRIPTS_DIR)/scripts/extract-env.ps1
SERVICE := ai-validation
ENV ?= local
OUT ?= .env
.DEFAULT_GOAL := help
.PHONY: help tools-check env
help: ## Show the available commands
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target>\\n\\n"} /^[a-zA-Z_-]+:.*## / {printf "  %-16s %s\\n", $$1, $$2}' $(MAKEFILE_LIST)
tools-check: ## Verify that infra-scripts is installed
	@test -f "$(EXTRACT_ENV)" || { echo "error: infra-scripts was not found at $(ORG_SCRIPTS_DIR)"; exit 1; }
env: tools-check ## Generate .env from Infisical (ENV=local OUT=.env)
	$(ORG_SCRIPTS_POWERSHELL) -NoProfile -ExecutionPolicy Bypass -File "$(EXTRACT_ENV)" -Service "$(SERVICE)" -Environment "$(ENV)" -OutputPath "$(OUT)"
