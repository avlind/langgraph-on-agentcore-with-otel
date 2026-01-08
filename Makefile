# Makefile for LangGraph AgentCore project
# Run 'make help' to see available targets
# Uses uv for dependency management

.PHONY: help setup test lint local local-invoke deploy destroy clean status logs traces invoke ui set-profile clear-profile check-aws

# Load saved AWS profile from .aws-profile file if it exists (and PROFILE not explicitly set)
PROFILE ?= $(shell cat .aws-profile 2>/dev/null)

# Build profile argument if set (use ifneq to check for non-empty value)
ifneq ($(strip $(PROFILE)),)
PROFILE_ARG = --profile $(PROFILE)
AWS_PROFILE_PREFIX = AWS_PROFILE=$(PROFILE)
else
PROFILE_ARG =
AWS_PROFILE_PREFIX =
endif

# Local development port (override with: make local PORT=8081)
PORT ?= 8080

# AWS credential check - validates credentials and prints helpful messages
check-aws:
	@$(AWS_PROFILE_PREFIX) python3 scripts/check_aws_creds.py || exit 1

help: ## Show this help message
	@echo "Usage: make [target] [PROFILE=...] [PROMPT=\"...\"] [PORT=8080]"
	@echo ""
	@echo "Targets:"
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "Examples:"
	@echo "  make set-profile PROFILE=YourProfile  # Save profile for all commands"
	@echo "  make local                            # Start local dev server on port 8080"
	@echo "  make local PORT=8081                  # Start on different port"
	@echo "  make local-invoke PROMPT=\"Hello\"      # Test local server"
	@echo "  make deploy                           # Deploy agent to AWS"
	@echo "  make invoke                           # Test the deployed agent"
	@echo "  make traces                           # View traces (last 1 hour)"
	@echo "  make traces HOURS=2                   # View traces (last 2 hours)"
	@echo "  make logs                             # Tail runtime logs"
	@echo "  make clear-profile                    # Clear saved profile"

setup: ## Check prerequisites and install all dependencies
	@python3 scripts/check_prereqs.py || exit 1
	@echo ""
	uv sync --extra local --extra deploy --extra ui
	@echo ""
	@echo "Setup complete. All dependencies installed."
	@echo "Use 'make <target>' to run commands."

test: ## Run all tests
	uv run pytest

test-cov: ## Run tests with coverage report
	uv run pytest --cov=. --cov-report=term-missing

lint: ## Run linter and format check (ruff)
	uv run ruff check langgraph_agent_web_search.py cdk/ ui/
	uv run ruff format --check langgraph_agent_web_search.py cdk/ ui/

format: ## Format code and fix lint issues (ruff)
	uv run ruff check --fix langgraph_agent_web_search.py cdk/ ui/
	uv run ruff format langgraph_agent_web_search.py cdk/ ui/

local: check-aws ## Start local dev server (requires AWS creds for Bedrock)
	@if lsof -i :$(PORT) >/dev/null 2>&1; then \
		echo "✗ Port $(PORT) is already in use"; \
		echo ""; \
		echo "Either stop the process using port $(PORT), or use a different port:"; \
		echo "  make local PORT=8081"; \
		echo "  make local-invoke PORT=8081 PROMPT=\"Hello\""; \
		exit 1; \
	fi
	@uv sync --extra local --quiet
	@$(AWS_PROFILE_PREFIX) uv run agentcore configure \
		-e langgraph_agent_web_search.py \
		-n langgraph_local_dev \
		-dt container \
		-r us-east-1 \
		--non-interactive
	$(AWS_PROFILE_PREFIX) uv run agentcore dev --port $(PORT)

local-invoke: ## Invoke local server (PROMPT="..." PORT=8080 optional)
	$(AWS_PROFILE_PREFIX) uv run --extra local agentcore invoke --dev --port $(PORT) '{"prompt": "$(PROMPT)"}'

deploy: check-aws ## Deploy agent to AWS
	@uv sync --extra deploy --quiet
	uv run python -m scripts.deploy $(PROFILE_ARG)

destroy: check-aws ## Destroy all resources (alias for destroy-all)
	@uv sync --extra deploy --quiet
	uv run python -m scripts.destroy $(PROFILE_ARG) --force

destroy-all: check-aws ## Destroy all resources including secret and ECR
	@uv sync --extra deploy --quiet
	uv run python -m scripts.destroy $(PROFILE_ARG) --force

status: check-aws ## Check agent runtime status
	@$(AWS_PROFILE_PREFIX) aws bedrock-agentcore-control list-agent-runtimes --output table

logs: check-aws ## Tail runtime logs for the agent (pretty formatted)
	@AGENT_NAME=$$(grep '^AGENT_NAME=' .env | cut -d'=' -f2) && \
	RUNTIME_ID=$$($(AWS_PROFILE_PREFIX) aws bedrock-agentcore-control list-agent-runtimes --output json --query "agentRuntimes[?agentRuntimeName=='$$AGENT_NAME'].agentRuntimeId" | jq -r '.[0]') && \
	if [ "$$RUNTIME_ID" != "null" ] && [ -n "$$RUNTIME_ID" ]; then \
		$(AWS_PROFILE_PREFIX) aws logs tail "/aws/bedrock-agentcore/runtimes/$$RUNTIME_ID-DEFAULT" --follow --region $$(grep '^AWS_REGION=' .env | cut -d'=' -f2) | python3 scripts/format_logs.py; \
	else \
		echo "✗ Agent runtime not found: $$AGENT_NAME"; \
		echo ""; \
		echo "Make sure the agent is deployed. Run:"; \
		echo "  make status PROFILE=$(PROFILE)"; \
		exit 1; \
	fi

traces: check-aws ## View OpenTelemetry traces from recent invocations (HOURS=1)
	@AGENT_NAME=$$(grep '^AGENT_NAME=' .env | cut -d'=' -f2) && \
	AWS_REGION=$$(grep '^AWS_REGION=' .env | cut -d'=' -f2) && \
	RUNTIME_ID=$$($(AWS_PROFILE_PREFIX) aws bedrock-agentcore-control list-agent-runtimes --output json --query "agentRuntimes[?agentRuntimeName=='$$AGENT_NAME'].agentRuntimeId" | jq -r '.[0]') && \
	MILLISECONDS=$$(($(HOURS) * 3600 * 1000)) && \
	if [ "$$RUNTIME_ID" != "null" ] && [ -n "$$RUNTIME_ID" ]; then \
		echo "🔍 Analyzing traces for agent: $$AGENT_NAME ($$RUNTIME_ID)"; \
		echo "   Time range: Last $(HOURS) hour(s)"; \
		echo ""; \
		$(AWS_PROFILE_PREFIX) aws logs filter-log-events \
			--log-group-name "/aws/bedrock-agentcore/runtimes/$$RUNTIME_ID-DEFAULT" \
			--start-time $$((($$(date +%s) * 1000) - $$MILLISECONDS)) \
			--region $$AWS_REGION \
			--output json \
			--query 'events[*].[timestamp, message]' | python3 scripts/analyze_traces.py; \
	else \
		echo "✗ Agent runtime not found: $$AGENT_NAME"; \
		echo ""; \
		echo "Make sure the agent is deployed. Run:"; \
		echo "  make status PROFILE=$(PROFILE)"; \
		exit 1; \
	fi

# Default prompt for invoke (override with: make invoke PROMPT="your prompt")
PROMPT ?= What is the weather in Seattle?

# Default hours for traces (override with: make traces HOURS=2)
HOURS ?= 1

invoke: check-aws ## Test the deployed agent
	@uv sync --extra deploy --quiet
	uv run python -m scripts.invoke $(PROFILE_ARG) --prompt "$(PROMPT)"

ui: check-aws ## Launch the agent testing web UI
	@uv sync --extra ui --extra deploy --quiet
	uv run python -m ui.app

synth: check-aws ## Synthesize CDK stacks (for debugging)
	cd cdk && $(AWS_PROFILE_PREFIX) cdk synth

clean: ## Remove build artifacts and cache files
	rm -rf .pytest_cache
	rm -rf __pycache__
	rm -rf cdk/cdk.out cdk/cdk-outputs.json
	rm -rf .venv
	rm -rf .bedrock_agentcore.yaml .bedrock_agentcore/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

set-profile: ## Save AWS profile for all commands (PROFILE=YourProfile)
ifndef PROFILE
	@echo "Usage: make set-profile PROFILE=YourProfile"
	@exit 1
endif
	@AWS_PROFILE=$(PROFILE) python3 scripts/check_aws_creds.py --interactive && \
		echo "$(PROFILE)" > .aws-profile && \
		echo "" && \
		echo "All make commands will now use this profile." && \
		echo "Run 'make clear-profile' to remove."

clear-profile: ## Clear saved AWS profile
	@rm -f .aws-profile
	@echo "✓ AWS profile cleared. Commands will use default credentials."
