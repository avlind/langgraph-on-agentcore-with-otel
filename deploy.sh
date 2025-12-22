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
while [[ $# -gt 0 ]]; do
    case $1 in
        --profile)
            AWS_PROFILE_ARG="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: ./deploy.sh [--profile AWS_PROFILE_NAME]"
            echo ""
            echo "Options:"
            echo "  --profile    AWS CLI profile name (for SSO users)"
            echo "  -h, --help   Show this help message"
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
    print_error ".env file not found. Copy .env.sample to .env and configure it."
    exit 1
fi

# Set AWS_PROFILE if provided
if [ -n "$AWS_PROFILE_ARG" ]; then
    export AWS_PROFILE="$AWS_PROFILE_ARG"
fi

# Set defaults if not in .env
AWS_REGION="${AWS_REGION:-us-east-2}"
AGENT_NAME="${AGENT_NAME:-langgraph_agent_web_search}"
MODEL_ID="${MODEL_ID:-global.anthropic.claude-haiku-4-5-20251001-v1:0}"
SECRET_NAME="${SECRET_NAME:-langgraph-agent/tavily-api-key}"

# Validate required variables
if [ -z "$TAVILY_API_KEY" ]; then
    print_error "TAVILY_API_KEY is not set in .env file"
    exit 1
fi

# Check if agentcore CLI is available
if ! command -v agentcore &> /dev/null; then
    print_error "agentcore command not found."
    echo ""
    echo "   The virtual environment may not be activated. Run:"
    echo ""
    echo "      source .venv/bin/activate"
    echo ""
    echo "   Or if you haven't installed dependencies yet:"
    echo ""
    echo "      python3 -m venv .venv"
    echo "      source .venv/bin/activate"
    echo "      pip install -r requirements.txt"
    echo ""
    exit 1
fi

# Header
echo -e "${BLUE}🚀 LangGraph Agent Deployment${NC}"
echo "=============================="
echo -e "${BLUE}📋 Configuration:${NC}"
echo "   Region: $AWS_REGION"
echo "   Agent:  $AGENT_NAME"
echo "   Model:  $MODEL_ID"
echo "   Secret: $SECRET_NAME"
if [ -n "$AWS_PROFILE_ARG" ]; then
    echo "   Profile: $AWS_PROFILE_ARG"
fi

# Build AWS CLI base command
AWS_CMD="aws"
if [ -n "$AWS_PROFILE_ARG" ]; then
    AWS_CMD="aws --profile $AWS_PROFILE_ARG"
fi

# Step 1: Check/Create Secrets Manager secret
print_step "1/4" "Checking Secrets Manager..."

SECRET_EXISTS=$($AWS_CMD secretsmanager describe-secret \
    --secret-id "$SECRET_NAME" \
    --region "$AWS_REGION" 2>/dev/null || echo "NOT_FOUND")

if [[ "$SECRET_EXISTS" == "NOT_FOUND" ]]; then
    print_warning "Secret not found, creating..."
    $AWS_CMD secretsmanager create-secret \
        --name "$SECRET_NAME" \
        --secret-string "$TAVILY_API_KEY" \
        --region "$AWS_REGION" > /dev/null
    print_success "Secret created: $SECRET_NAME"
else
    print_success "Secret already exists, skipping creation"
fi

# Step 2: Configure agent
print_step "2/4" "Configuring agent..."

# Build agentcore command with profile if needed
if [ -n "$AWS_PROFILE_ARG" ]; then
    AGENTCORE_PREFIX="AWS_PROFILE=$AWS_PROFILE_ARG"
else
    AGENTCORE_PREFIX=""
fi

eval $AGENTCORE_PREFIX agentcore configure \
    -e langgraph_agent_web_search.py \
    -n "$AGENT_NAME" \
    -dt container \
    -r "$AWS_REGION" \
    --non-interactive > /dev/null 2>&1

print_success "Agent configured for container deployment"

# Step 3: Deploy agent
print_step "3/4" "Deploying to AgentCore (this may take several minutes)..."

# Pass environment variables via --env flag (no Dockerfile injection needed)
eval $AGENTCORE_PREFIX agentcore deploy \
    --auto-update-on-conflict \
    --env "AWS_REGION=$AWS_REGION" \
    --env "SECRET_NAME=$SECRET_NAME" \
    --env "MODEL_ID=$MODEL_ID"

print_success "Deployment complete"

# Step 4: Grant IAM permissions for Secrets Manager
print_step "4/4" "Granting IAM permissions..."

# Extract role name from config for the specific agent
# The YAML structure has agents listed by name, we need to find our agent's execution_role
ROLE_ARN=$(awk -v agent="$AGENT_NAME" '
    $0 ~ "^  " agent ":" { in_agent=1 }
    in_agent && /execution_role:.*Runtime/ { print $2; exit }
' .bedrock_agentcore.yaml)
ROLE_NAME=$(echo "$ROLE_ARN" | sed 's/.*role\///')

# Check if policy already exists
POLICY_EXISTS=$($AWS_CMD iam get-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name SecretsManagerAccess \
    --region "$AWS_REGION" 2>/dev/null || echo "NOT_FOUND")

if [[ "$POLICY_EXISTS" == "NOT_FOUND" ]]; then
    # Get AWS account ID for the policy
    ACCOUNT_ID=$($AWS_CMD sts get-caller-identity --query Account --output text)

    $AWS_CMD iam put-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-name SecretsManagerAccess \
        --policy-document "{
            \"Version\": \"2012-10-17\",
            \"Statement\": [
                {
                    \"Effect\": \"Allow\",
                    \"Action\": [\"secretsmanager:GetSecretValue\"],
                    \"Resource\": \"arn:aws:secretsmanager:$AWS_REGION:$ACCOUNT_ID:secret:${SECRET_NAME}*\"
                }
            ]
        }" \
        --region "$AWS_REGION"
    print_success "Secrets Manager access granted to execution role"
else
    print_success "IAM policy already exists, skipping"
fi

# Success message
echo ""
echo -e "${GREEN}✅ Deployment successful!${NC}"
echo ""
echo "Next steps:"
if [ -n "$AWS_PROFILE_ARG" ]; then
    echo "   Test: AWS_PROFILE=$AWS_PROFILE_ARG agentcore invoke '{\"prompt\": \"Search for AWS news\"}'"
    echo "   Logs: AWS_PROFILE=$AWS_PROFILE_ARG agentcore logs --follow"
    echo "   Traces: AWS_PROFILE=$AWS_PROFILE_ARG agentcore obs list"
else
    echo "   Test: agentcore invoke '{\"prompt\": \"Search for AWS news\"}'"
    echo "   Logs: agentcore logs --follow"
    echo "   Traces: agentcore obs list"
fi
