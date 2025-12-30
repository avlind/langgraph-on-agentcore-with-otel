# Makefile for LangGraph AgentCore project
# Run 'make help' to see available targets
# Uses uv for dependency management

.PHONY: help setup test lint deploy destroy clean status logs invoke

# Default AWS profile (override with: make deploy PROFILE=YourProfile)
PROFILE ?=

# Build profile argument if set
ifdef PROFILE
PROFILE_ARG = --profile $(PROFILE)
AWS_PROFILE_PREFIX = AWS_PROFILE=$(PROFILE)
else
PROFILE_ARG =
AWS_PROFILE_PREFIX =
endif

help: ## Show this help message
	@echo "Usage: make [target] [PROFILE=YourAWSProfile]"
	@echo ""
	@echo "Targets:"
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "Examples:"
	@echo "  make setup                    # Install dependencies with uv"
	@echo "  make test                     # Run all tests"
	@echo "  make deploy PROFILE=PowerUser # Deploy with AWS profile"
	@echo "  make invoke PROFILE=PowerUser # Test the deployed agent"

setup: ## Install dependencies with uv
	uv sync --extra deploy
	@echo ""
	@echo "Setup complete. Dependencies installed."
	@echo "Use 'uv run <command>' or 'make <target>' to run commands."

test: ## Run all tests
	uv run pytest

test-cov: ## Run tests with coverage report
	uv run pytest --cov=. --cov-report=term-missing

lint: ## Run linter and format check (ruff)
	uv run ruff check langgraph_agent_web_search.py resilience.py cdk/
	uv run ruff format --check langgraph_agent_web_search.py resilience.py cdk/

format: ## Format code and fix lint issues (ruff)
	uv run ruff check --fix langgraph_agent_web_search.py resilience.py cdk/
	uv run ruff format langgraph_agent_web_search.py resilience.py cdk/

deploy: ## Deploy agent to AWS (use PROFILE=name for SSO)
	uv run ./deploy.sh $(PROFILE_ARG)

destroy: ## Destroy agent only (keeps secret and ECR)
	uv run ./destroy.sh $(PROFILE_ARG)

destroy-all: ## Destroy all resources including secret and ECR
	uv run ./destroy.sh $(PROFILE_ARG) --all

status: ## Check agent status
	$(AWS_PROFILE_PREFIX) uv run agentcore status

logs: ## Tail agent logs
	$(AWS_PROFILE_PREFIX) uv run agentcore logs --follow

traces: ## List recent traces
	$(AWS_PROFILE_PREFIX) uv run agentcore obs list

invoke: ## Test the deployed agent
	$(AWS_PROFILE_PREFIX) uv run agentcore invoke '{"prompt": "What is the weather in Seattle?"}'

clean: ## Remove build artifacts and cache files
	rm -rf .pytest_cache
	rm -rf __pycache__
	rm -rf cdk/cdk.out
	rm -rf .venv
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
