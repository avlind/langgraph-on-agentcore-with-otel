#!/bin/bash
set -e
set -o pipefail

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

# Cleanup function for partial failures
cleanup_on_failure() {
    print_error "Deployment failed. You may need to run ./destroy.sh to clean up partial resources."
}
trap cleanup_on_failure ERR

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
FALLBACK_MODEL_ID="${FALLBACK_MODEL_ID:-global.anthropic.claude-sonnet-4-5-20250929-v1:0}"
SECRET_NAME="${SECRET_NAME:-langgraph-agent/tavily-api-key}"

# Validate required variables
validate_config() {
    local errors=0

    if [ -z "$TAVILY_API_KEY" ]; then
        print_error "TAVILY_API_KEY is not set in .env file"
        errors=$((errors + 1))
    fi

    # Validate AWS_REGION format (e.g., us-east-2, eu-west-1)
    if ! [[ "$AWS_REGION" =~ ^[a-z]{2}-[a-z]+-[0-9]+$ ]]; then
        print_error "Invalid AWS_REGION format: $AWS_REGION (expected format: us-east-2)"
        errors=$((errors + 1))
    fi

    # Validate AGENT_NAME (alphanumeric and underscores only)
    if ! [[ "$AGENT_NAME" =~ ^[a-zA-Z0-9_]+$ ]]; then
        print_error "Invalid AGENT_NAME: $AGENT_NAME (use only alphanumeric and underscores)"
        errors=$((errors + 1))
    fi

    if [ $errors -gt 0 ]; then
        exit 1
    fi
}

validate_config

# Check if agentcore CLI is available
if ! command -v agentcore &> /dev/null; then
    print_error "agentcore command not found."
    echo ""
    echo "   Run this script via uv or make:"
    echo ""
    echo "      uv run ./deploy.sh --profile YourProfile"
    echo "      # or"
    echo "      make deploy PROFILE=YourProfile"
    echo ""
    echo "   If dependencies aren't installed yet:"
    echo ""
    echo "      uv sync"
    echo ""
    exit 1
fi

# Check if CDK is available
if ! command -v cdk &> /dev/null; then
    print_error "AWS CDK CLI not found."
    echo ""
    echo "   Install it globally with:"
    echo ""
    echo "      npm install -g aws-cdk"
    echo ""
    exit 1
fi

# Build AWS CLI base command (needed for bootstrap check)
AWS_CMD="aws"
if [ -n "$AWS_PROFILE_ARG" ]; then
    AWS_CMD="aws --profile $AWS_PROFILE_ARG"
fi

# Check if CDK is bootstrapped in this account/region
BOOTSTRAP_CHECK=$($AWS_CMD cloudformation describe-stacks \
    --stack-name CDKToolkit \
    --region "$AWS_REGION" 2>/dev/null || echo "NOT_FOUND")

if [[ "$BOOTSTRAP_CHECK" == "NOT_FOUND" ]]; then
    print_warning "CDK not bootstrapped in this account/region."
    echo ""
    echo "   Bootstrapping CDK (one-time setup)..."
    ACCOUNT_ID=$($AWS_CMD sts get-caller-identity --query Account --output text)
    if ! cdk bootstrap "aws://$ACCOUNT_ID/$AWS_REGION"; then
        print_error "CDK bootstrap failed"
        exit 1
    fi
    print_success "CDK bootstrapped successfully"
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

# Build agentcore command prefix
if [ -n "$AWS_PROFILE_ARG" ]; then
    AGENTCORE_PREFIX="AWS_PROFILE=$AWS_PROFILE_ARG"
else
    AGENTCORE_PREFIX=""
fi

# Step 1: Deploy Secrets Manager secret via CDK
print_step "1/5" "Deploying Secrets Manager secret (CDK)..."

cd cdk
# Run CDK deploy and capture exit code (don't use pipefail for CDK output)
set +o pipefail
cdk deploy SecretsStack \
    --context secret_name="$SECRET_NAME" \
    --context tavily_api_key="$TAVILY_API_KEY" \
    --require-approval never \
    --outputs-file cdk-outputs.json 2>&1 | grep -v "^$" || true
CDK_EXIT=${PIPESTATUS[0]}
set -o pipefail
cd ..

# Verify SecretsStack deployment succeeded
if [ "$CDK_EXIT" -ne 0 ] || ! $AWS_CMD cloudformation describe-stacks \
    --stack-name SecretsStack \
    --region "$AWS_REGION" &>/dev/null; then
    print_error "SecretsStack deployment failed"
    exit 1
fi

print_success "Secret deployed via CDK"

# Step 2: Configure agent
print_step "2/5" "Configuring agent..."

CONFIGURE_OUTPUT=$(eval $AGENTCORE_PREFIX agentcore configure \
    -e langgraph_agent_web_search.py \
    -n "$AGENT_NAME" \
    -dt container \
    -r "$AWS_REGION" \
    --non-interactive 2>&1) || {
    print_error "Agent configuration failed"
    echo "$CONFIGURE_OUTPUT"
    exit 1
}

print_success "Agent configured for container deployment"

# Step 3: Deploy agent
print_step "3/5" "Deploying to AgentCore (this may take several minutes)..."

# Pass environment variables via --env flag (no Dockerfile injection needed)
eval $AGENTCORE_PREFIX agentcore deploy \
    --auto-update-on-conflict \
    --env "AWS_REGION=$AWS_REGION" \
    --env "SECRET_NAME=$SECRET_NAME" \
    --env "MODEL_ID=$MODEL_ID" \
    --env "FALLBACK_MODEL_ID=$FALLBACK_MODEL_ID"

print_success "Deployment complete"

# Step 4: Extract execution role ARN
print_step "4/5" "Extracting execution role ARN..."

if [ ! -f .bedrock_agentcore.yaml ]; then
    print_error ".bedrock_agentcore.yaml not found after deployment"
    exit 1
fi

ROLE_ARN=$(awk -v agent="$AGENT_NAME" '
    $0 ~ "^  " agent ":" { in_agent=1 }
    in_agent && /execution_role:.*Runtime/ { print $2; exit }
' .bedrock_agentcore.yaml)

if [ -z "$ROLE_ARN" ]; then
    print_error "Could not extract execution role ARN from .bedrock_agentcore.yaml"
    echo "   Check that agent '$AGENT_NAME' exists in the config file"
    exit 1
fi

print_success "Found role: $ROLE_ARN"

# Get secret ARN from CDK outputs
SECRET_ARN=$($AWS_CMD cloudformation describe-stacks \
    --stack-name SecretsStack \
    --query "Stacks[0].Outputs[?OutputKey=='SecretArn'].OutputValue" \
    --output text \
    --region "$AWS_REGION")

if [ -z "$SECRET_ARN" ] || [ "$SECRET_ARN" = "None" ]; then
    print_error "Could not retrieve Secret ARN from CloudFormation outputs"
    exit 1
fi

print_success "Found secret: $SECRET_ARN"

# Step 5: Grant IAM permissions via CDK
print_step "5/5" "Granting IAM permissions (CDK)..."

cd cdk
# Run CDK deploy and capture exit code (don't use pipefail for CDK output)
set +o pipefail
cdk deploy IamPolicyStack \
    --context execution_role_arn="$ROLE_ARN" \
    --context secret_arn="$SECRET_ARN" \
    --require-approval never 2>&1 | grep -v "^$" || true
CDK_EXIT=${PIPESTATUS[0]}
set -o pipefail
cd ..

# Verify IamPolicyStack deployment succeeded
if [ "$CDK_EXIT" -ne 0 ] || ! $AWS_CMD cloudformation describe-stacks \
    --stack-name IamPolicyStack \
    --region "$AWS_REGION" &>/dev/null; then
    print_error "IamPolicyStack deployment failed"
    exit 1
fi

print_success "IAM policy attached via CDK"

# Clear the error trap on success
trap - ERR

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
