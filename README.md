# LangGraph Agent on AWS Bedrock AgentCore

A sample LangGraph agent with web search capabilities deployed to AWS Bedrock AgentCore. This project demonstrates how to build and deploy a LangGraph-based AI agent with full observability (LLM calls, tool calls, and timing metrics) using AWS native tooling.

## What This Project Does

This agent:
- Uses **Claude Haiku** (via Amazon Bedrock) as the LLM
- Performs **web searches** using the Tavily API
- Runs on **AWS Bedrock AgentCore** with container deployment
- Provides **full observability** via OpenTelemetry instrumentation (LangChain traces, LLM latency, tool execution times)

## Architecture

```
User Request → Bedrock AgentCore → LangGraph Agent → Claude Haiku (Bedrock)
                                                   ↘ Tavily Search API
```

The agent uses a simple ReAct-style graph:
1. **Chatbot Node**: Invokes Claude Haiku with tools
2. **Tools Condition**: Routes to tools if LLM requests a tool call
3. **Tools Node**: Executes the Tavily search tool
4. Loop back to Chatbot until complete

## Prerequisites

- **AWS Account** with permissions for:
  - Bedrock AgentCore
  - IAM (create roles/policies)
  - ECR (container registry)
  - S3 (deployment artifacts)
  - CodeBuild (container builds)
  - Secrets Manager
  - CloudWatch Logs
- **AWS CLI** configured (either default credentials or a named profile)
- **Python 3.13+**
- **Tavily API Key** - Get one at https://tavily.com

> **Note on AWS Credentials:** Commands below show two options:
> - **Default credentials**: Use if you have `~/.aws/credentials` configured or are using environment variables
> - **Named profile**: Use if you have SSO or multiple profiles configured (replace `YourProfileName` with your profile)

## Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd langgraph-to-agentcore-sample
```

### 2. Create Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file from the sample:

```bash
cp .env.sample .env
```

Edit `.env` with your configuration:

```bash
# Required - API Keys
TAVILY_API_KEY=your-tavily-api-key-here

# Deployment Configuration
AWS_REGION=us-east-2
AGENT_NAME=langgraph_agent_web_search
MODEL_ID=global.anthropic.claude-haiku-4-5-20251001-v1:0
SECRET_NAME=langgraph-agent/tavily-api-key
```

| Variable | Description |
|----------|-------------|
| `TAVILY_API_KEY` | Your Tavily API key (required) |
| `AWS_REGION` | AWS region for deployment (default: `us-east-2`) |
| `AGENT_NAME` | Name for your agent in AgentCore |
| `MODEL_ID` | Bedrock model ID to use |
| `SECRET_NAME` | Name for the Secrets Manager secret |

### 4. Ensure AWS Credentials are Active

```bash
# For SSO profiles
aws sso login --profile YourProfileName

# For default credentials, verify with:
aws sts get-caller-identity
```

## Deployment

### Using deploy.sh (Required)

The `deploy.sh` script is **required** for deployment because it passes runtime environment variables to the AgentCore container via `--env` flags. Without this step, the agent would use hardcoded defaults instead of your `.env` configuration.

> **Important:** Make sure your virtual environment is activated before running the scripts:
> ```bash
> source .venv/bin/activate
> ```

```bash
# Using default credentials
./deploy.sh

# Using a named AWS profile (SSO users)
./deploy.sh --profile YourProfileName
```

**What the script does:**

| Step | Action |
|------|--------|
| 1/4 | **Secrets Manager** - Creates the API key secret (if it doesn't exist) |
| 2/4 | **Configure** - Runs `agentcore configure` to generate Dockerfile |
| 3/4 | **Deploy** - Builds container via CodeBuild, passes env vars via `--env` flags |
| 4/4 | **IAM permissions** - Grants Secrets Manager access to execution role |

> **How environment variables are passed:** The script uses `agentcore deploy --env` flags to pass `AWS_REGION`, `SECRET_NAME`, and `MODEL_ID` to the container runtime. This approach is cleaner than modifying the Dockerfile.

### Manual Deployment (Advanced)

<details>
<summary>Click to expand manual deployment steps</summary>

> **Warning:** Manual deployment requires you to pass environment variables via `--env` flags when running `agentcore deploy`. If you skip this step, the agent will use hardcoded defaults instead of your configuration. **Using `deploy.sh` is strongly recommended.**

#### 1. Create Secrets Manager Secret

```bash
# Using default credentials
aws secretsmanager create-secret \
  --name "langgraph-agent/tavily-api-key" \
  --secret-string "your-tavily-api-key-here" \
  --region us-east-2

# Using a named profile
aws secretsmanager create-secret \
  --name "langgraph-agent/tavily-api-key" \
  --secret-string "your-tavily-api-key-here" \
  --region us-east-2 \
  --profile YourProfileName
```

#### 2. Configure the Agent

```bash
# Using default credentials
agentcore configure \
  -e langgraph_agent_web_search.py \
  -n langgraph_agent_web_search \
  -dt container \
  -r us-east-2 \
  --non-interactive

# Using a named profile
AWS_PROFILE=YourProfileName agentcore configure \
  -e langgraph_agent_web_search.py \
  -n langgraph_agent_web_search \
  -dt container \
  -r us-east-2 \
  --non-interactive
```

**Arguments explained:**

| Flag | Description |
|------|-------------|
| `-e, --entrypoint` | The Python file containing your agent code and the `@app.entrypoint` decorator |
| `-n, --name` | Unique name for your agent (used in ARNs, ECR repo names, and CloudWatch logs) |
| `-dt, --deployment-type` | Either `container` or `direct_code_deploy`. Use `container` for proper OpenTelemetry instrumentation—this wraps your code with `opentelemetry-instrument` in the Dockerfile |
| `-r, --region` | AWS region to deploy to (must have Bedrock AgentCore available) |
| `--non-interactive` | Skip interactive prompts; use defaults for unspecified options (useful for CI/CD) |

> **Why `container` mode?** The `direct_code_deploy` mode runs your Python file directly without the `opentelemetry-instrument` wrapper. Container mode generates a Dockerfile with `CMD ["opentelemetry-instrument", "python", "-m", "your_agent"]`, which auto-instruments LangChain, Bedrock, and other libraries for tracing.

#### 3. Deploy the Agent

Pass environment variables via `--env` flags:

```bash
# Using default credentials
agentcore deploy \
  --env "AWS_REGION=us-east-2" \
  --env "SECRET_NAME=langgraph-agent/tavily-api-key" \
  --env "MODEL_ID=global.anthropic.claude-haiku-4-5-20251001-v1:0"

# Using a named profile
AWS_PROFILE=YourProfileName agentcore deploy \
  --env "AWS_REGION=us-east-2" \
  --env "SECRET_NAME=langgraph-agent/tavily-api-key" \
  --env "MODEL_ID=global.anthropic.claude-haiku-4-5-20251001-v1:0"
```

#### 4. Grant Secrets Manager Access

```bash
# Get the execution role name from .bedrock_agentcore.yaml
ROLE_NAME=$(grep "execution_role:" .bedrock_agentcore.yaml | head -1 | sed 's/.*role\///' | tr -d ' ')

# Using default credentials
aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name SecretsManagerAccess \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": ["secretsmanager:GetSecretValue"],
        "Resource": "arn:aws:secretsmanager:us-east-2:*:secret:langgraph-agent/*"
      }
    ]
  }' \
  --region us-east-2

# Using a named profile
aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name SecretsManagerAccess \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": ["secretsmanager:GetSecretValue"],
        "Resource": "arn:aws:secretsmanager:us-east-2:*:secret:langgraph-agent/*"
      }
    ]
  }' \
  --region us-east-2 \
  --profile YourProfileName
```

</details>

## Testing

### Invoke the Agent

```bash
# Using default credentials
agentcore invoke '{"prompt": "Search for AWS news today"}'

# Using a named profile
AWS_PROFILE=YourProfileName agentcore invoke '{"prompt": "Search for AWS news today"}'
```

### View Logs

```bash
# Using default credentials
agentcore logs --follow

# Using a named profile
AWS_PROFILE=YourProfileName agentcore logs --follow
```

Or use AWS CLI directly:

```bash
# Using default credentials
aws logs tail /aws/bedrock-agentcore/runtimes/<agent-id>-DEFAULT \
  --log-stream-name-prefix "$(date +%Y/%m/%d)/[runtime-logs]" \
  --follow \
  --region us-east-2

# Using a named profile
aws logs tail /aws/bedrock-agentcore/runtimes/<agent-id>-DEFAULT \
  --log-stream-name-prefix "$(date +%Y/%m/%d)/[runtime-logs]" \
  --follow \
  --region us-east-2 \
  --profile YourProfileName
```

### Check Agent Status

```bash
# Using default credentials
agentcore status

# Using a named profile
AWS_PROFILE=YourProfileName agentcore status
```

## Observability

This project uses OpenTelemetry instrumentation to capture LangChain traces. The container deployment uses the `opentelemetry-instrument` wrapper which auto-instruments:

- **LangChain/LangGraph** operations (chains, tools, routing)
- **Bedrock Runtime** API calls (LLM invocations)
- **Botocore** AWS SDK calls

### View Traces

List recent traces:

```bash
# Using default credentials
agentcore obs list

# Using a named profile
AWS_PROFILE=YourProfileName agentcore obs list
```

Show detailed trace with timing:

```bash
# Using default credentials
agentcore obs show --last 1 --verbose

# Using a named profile
AWS_PROFILE=YourProfileName agentcore obs show --last 1 --verbose
```

Example output:
```
🔍 Trace: 694561e74067881e... (6 spans, 4293.24ms)
├── ⚠ chatbot.task [1197.63ms]
│   ├── ⚠ ChatBedrockConverse.chat [1196.88ms]
│   │   └── ⚠ chat claude-haiku [1192.09ms]
│   └── ⚠ tools_condition.task [0.24ms]
└── ⚠ tools.task [3095.05ms]
    └── ⚠ tavily_search_results_json.tool [3093.94ms]
```

### CloudWatch Dashboard

View the GenAI Observability Dashboard in the AWS Console:

```
https://console.aws.amazon.com/cloudwatch/home?region=us-east-2#gen-ai-observability/agent-core
```

## Project Structure

```
.
├── langgraph_agent_web_search.py  # Main agent code
├── deploy.sh                      # One-command deployment script
├── destroy.sh                     # Cleanup script
├── requirements.txt               # Python dependencies
├── .env.sample                    # Environment variable template
├── .env                           # Local environment variables (gitignored)
├── .gitignore                     # Git ignore rules
├── .bedrock_agentcore.yaml        # Agent configuration (generated)
└── .bedrock_agentcore/            # Build artifacts (generated)
    └── langgraph_agent_web_search/
        └── Dockerfile             # Container definition
```

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `langgraph` | Agent graph framework |
| `langchain` | LLM abstraction layer |
| `langchain-aws` | Bedrock integration |
| `langchain-community` | Tavily search tool |
| `tavily-python` | Tavily API client |
| `bedrock-agentcore` | AgentCore runtime SDK |
| `bedrock-agentcore-starter-toolkit` | CLI tools |
| `opentelemetry-instrumentation-langchain` | LangChain tracing |
| `aws-opentelemetry-distro` | AWS OTEL distribution |

## Cleanup

Use the cleanup script to destroy AWS resources:

```bash
# Destroy agent only (keeps secret and ECR for faster redeployment)
./destroy.sh

# Destroy agent with a named profile
./destroy.sh --profile YourProfileName

# Destroy everything (agent + secret + ECR repository)
./destroy.sh --all

# Or selectively delete additional resources
./destroy.sh --delete-secret              # Also delete Secrets Manager secret
./destroy.sh --delete-ecr                 # Also delete ECR repository
./destroy.sh --delete-secret --delete-ecr # Same as --all
```

**What gets deleted:**

| Flag | Resources Removed |
|------|-------------------|
| *(default)* | AgentCore agent, endpoint, memory, IAM roles, S3 artifacts, ECR images |
| `--delete-secret` | + Secrets Manager secret |
| `--delete-ecr` | + ECR repository |
| `--all` | Everything above |

> **Tip:** For iterative development, use `./destroy.sh` without flags. This preserves your secret and ECR repo, making redeployment faster since these don't need to be recreated.

## Troubleshooting

### "agentcore command not found"

The virtual environment is not activated. Run:

```bash
source .venv/bin/activate
```

### Agent fails to start with "TAVILY_API_KEY not found"

Ensure:
1. The secret exists in Secrets Manager with the correct name
2. The execution role has the `SecretsManagerAccess` policy attached

### Traces not appearing in `agentcore obs list`

1. Wait 1-2 minutes after invocation for traces to propagate
2. Verify deployment type is `container` (not `direct_code_deploy`)
3. Check the OTEL logs: `aws logs tail <log-group> --log-stream-names "otel-rt-logs"`

### CodeBuild fails

Check CodeBuild logs in the AWS Console or run:

```bash
# Using default credentials
agentcore logs --build

# Using a named profile
AWS_PROFILE=YourProfileName agentcore logs --build
```

## References

- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Tavily API](https://tavily.com)
- [AWS Bedrock AgentCore Samples](https://github.com/awslabs/amazon-bedrock-agentcore-samples)
