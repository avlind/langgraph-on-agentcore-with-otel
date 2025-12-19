#!/bin/bash
set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_step() {
    echo -e "\n${BLUE}[$1]${NC} $2"
}

print_success() {
    echo -e "   ${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "   ${YELLOW}!${NC} $1"
}

print_error() {
    echo -e "   ${RED}✗${NC} $1"
}

# Parse arguments
AWS_PROFILE_ARG=""
DELETE_SECRET=false
DELETE_ECR=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --profile)
            AWS_PROFILE_ARG="$2"
            shift 2
            ;;
        --delete-secret)
            DELETE_SECRET=true
            shift
            ;;
        --delete-ecr)
            DELETE_ECR=true
            shift
            ;;
        --all)
            DELETE_SECRET=true
            DELETE_ECR=true
            shift
            ;;
        -h|--help)
            echo "Usage: ./destroy.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --profile NAME    AWS CLI profile name (for SSO users)"
            echo "  --delete-secret   Also delete the Secrets Manager secret"
            echo "  --delete-ecr      Also delete the ECR repository"
            echo "  --all             Delete everything (agent + secret + ECR)"
            echo "  -h, --help        Show this help message"
            echo ""
            echo "By default, only the AgentCore agent is destroyed."
            echo "The secret and ECR repo are preserved for faster redeployment."
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Load .env file
if [ -f .env ]; then
    set -a
    source .env
    set +a
else
    print_error ".env file not found. Cannot determine agent configuration."
    exit 1
fi

# Set AWS_PROFILE if provided
if [ -n "$AWS_PROFILE_ARG" ]; then
    export AWS_PROFILE="$AWS_PROFILE_ARG"
fi

# Set defaults if not in .env
AWS_REGION="${AWS_REGION:-us-east-2}"
AGENT_NAME="${AGENT_NAME:-langgraph_agent_web_search}"
SECRET_NAME="${SECRET_NAME:-langgraph-agent/tavily-api-key}"

# Check if agentcore CLI is available
if ! command -v agentcore &> /dev/null; then
    print_error "agentcore command not found."
    echo ""
    echo "   The virtual environment may not be activated. Run:"
    echo ""
    echo "      source .venv/bin/activate"
    echo ""
    exit 1
fi

# Build AWS CLI base command
AWS_CMD="aws"
if [ -n "$AWS_PROFILE_ARG" ]; then
    AWS_CMD="aws --profile $AWS_PROFILE_ARG"
fi

# Build agentcore command prefix
if [ -n "$AWS_PROFILE_ARG" ]; then
    AGENTCORE_PREFIX="AWS_PROFILE=$AWS_PROFILE_ARG"
else
    AGENTCORE_PREFIX=""
fi

# Calculate total steps
TOTAL_STEPS=1
if [ "$DELETE_SECRET" = true ]; then
    TOTAL_STEPS=$((TOTAL_STEPS + 1))
fi
if [ "$DELETE_ECR" = true ]; then
    TOTAL_STEPS=$((TOTAL_STEPS + 1))
fi

CURRENT_STEP=0

# Header
echo -e "${RED}🗑️  LangGraph Agent Cleanup${NC}"
echo "=============================="
echo -e "${BLUE}📋 Configuration:${NC}"
echo "   Region: $AWS_REGION"
echo "   Agent:  $AGENT_NAME"
if [ "$DELETE_SECRET" = true ]; then
    echo "   Secret: $SECRET_NAME (will be deleted)"
fi
if [ "$DELETE_ECR" = true ]; then
    echo "   ECR:    bedrock-agentcore-$AGENT_NAME (will be deleted)"
fi
if [ -n "$AWS_PROFILE_ARG" ]; then
    echo "   Profile: $AWS_PROFILE_ARG"
fi

# Step 1: Destroy AgentCore agent
CURRENT_STEP=$((CURRENT_STEP + 1))
print_step "$CURRENT_STEP/$TOTAL_STEPS" "Destroying AgentCore agent..."

# Check if agent exists in config
if [ -f .bedrock_agentcore.yaml ]; then
    eval $AGENTCORE_PREFIX agentcore destroy --agent "$AGENT_NAME" --force 2>&1 | grep -v "^$" || true
    print_success "Agent destroyed"
else
    print_warning "No .bedrock_agentcore.yaml found, agent may already be destroyed"
fi

# Step 2: Delete Secrets Manager secret (if requested)
if [ "$DELETE_SECRET" = true ]; then
    CURRENT_STEP=$((CURRENT_STEP + 1))
    print_step "$CURRENT_STEP/$TOTAL_STEPS" "Deleting Secrets Manager secret..."

    SECRET_EXISTS=$($AWS_CMD secretsmanager describe-secret \
        --secret-id "$SECRET_NAME" \
        --region "$AWS_REGION" 2>/dev/null || echo "NOT_FOUND")

    if [[ "$SECRET_EXISTS" != "NOT_FOUND" ]]; then
        $AWS_CMD secretsmanager delete-secret \
            --secret-id "$SECRET_NAME" \
            --force-delete-without-recovery \
            --region "$AWS_REGION" > /dev/null
        print_success "Secret deleted: $SECRET_NAME"
    else
        print_warning "Secret not found, skipping"
    fi
fi

# Step 3: Delete ECR repository (if requested)
if [ "$DELETE_ECR" = true ]; then
    CURRENT_STEP=$((CURRENT_STEP + 1))
    print_step "$CURRENT_STEP/$TOTAL_STEPS" "Deleting ECR repository..."

    ECR_REPO="bedrock-agentcore-$AGENT_NAME"

    ECR_EXISTS=$($AWS_CMD ecr describe-repositories \
        --repository-names "$ECR_REPO" \
        --region "$AWS_REGION" 2>/dev/null || echo "NOT_FOUND")

    if [[ "$ECR_EXISTS" != "NOT_FOUND" ]]; then
        $AWS_CMD ecr delete-repository \
            --repository-name "$ECR_REPO" \
            --region "$AWS_REGION" \
            --force > /dev/null
        print_success "ECR repository deleted: $ECR_REPO"
    else
        print_warning "ECR repository not found, skipping"
    fi
fi

# Success message
echo ""
echo -e "${GREEN}✅ Cleanup complete!${NC}"
echo ""
if [ "$DELETE_SECRET" = false ] || [ "$DELETE_ECR" = false ]; then
    echo "Resources preserved (use flags to delete):"
    if [ "$DELETE_SECRET" = false ]; then
        echo "   • Secrets Manager secret (--delete-secret)"
    fi
    if [ "$DELETE_ECR" = false ]; then
        echo "   • ECR repository (--delete-ecr)"
    fi
    echo ""
    echo "To delete everything: ./destroy.sh --all"
fi
