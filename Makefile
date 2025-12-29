# Makefile for LangGraph AgentCore project
# Run 'make help' to see available targets

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
	@echo "  make setup                    # Create venv and install deps"
	@echo "  make test                     # Run all tests"
	@echo "  make deploy PROFILE=PowerUser # Deploy with AWS profile"
	@echo "  make invoke PROFILE=PowerUser # Test the deployed agent"

setup: ## Create virtual environment and install dependencies
	python3 -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt
	@echo ""
	@echo "Setup complete. Run: source .venv/bin/activate"

test: ## Run all tests
	. .venv/bin/activate && pytest tests/ -v

test-cov: ## Run tests with coverage report
	. .venv/bin/activate && pytest tests/ -v --cov=. --cov-report=term-missing

lint: ## Run linters (requires ruff and black)
	. .venv/bin/activate && ruff check langgraph_agent_web_search.py cdk/
	. .venv/bin/activate && black --check langgraph_agent_web_search.py cdk/

format: ## Format code with black
	. .venv/bin/activate && black langgraph_agent_web_search.py cdk/

deploy: ## Deploy agent to AWS (use PROFILE=name for SSO)
	. .venv/bin/activate && ./deploy.sh $(PROFILE_ARG)

destroy: ## Destroy agent only (keeps secret and ECR)
	. .venv/bin/activate && ./destroy.sh $(PROFILE_ARG)

destroy-all: ## Destroy all resources including secret and ECR
	. .venv/bin/activate && ./destroy.sh $(PROFILE_ARG) --all

status: ## Check agent status
	. .venv/bin/activate && $(AWS_PROFILE_PREFIX) agentcore status

logs: ## Tail agent logs
	. .venv/bin/activate && $(AWS_PROFILE_PREFIX) agentcore logs --follow

traces: ## List recent traces
	. .venv/bin/activate && $(AWS_PROFILE_PREFIX) agentcore obs list

invoke: ## Test the deployed agent
	. .venv/bin/activate && $(AWS_PROFILE_PREFIX) agentcore invoke '{"prompt": "What is the weather in Seattle?"}'

clean: ## Remove build artifacts and cache files
	rm -rf .pytest_cache
	rm -rf __pycache__
	rm -rf cdk/cdk.out
	rm -rf .venv
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
