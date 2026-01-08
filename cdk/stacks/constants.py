"""Constants used across CDK stacks."""

# Stack names - used in deploy and destroy scripts
SECRETS_STACK_NAME = "SecretsStack"
IAM_POLICY_STACK_NAME = "IamPolicyStack"  # Deprecated
AGENT_INFRA_STACK_NAME = "AgentInfraStack"  # ECR, CodeBuild, IAM
MEMORY_STACK_NAME = "MemoryStack"  # AgentCore Memory (parallel with CodeBuild)
RUNTIME_STACK_NAME = "RuntimeStack"  # AgentCore Runtime only

# Resource identifiers
SECRETS_MANAGER_POLICY_NAME = "SecretsManagerAccess"

# CDK context keys - passed via --context flags from deploy script
CONTEXT_SECRET_NAME = "secret_name"
CONTEXT_TAVILY_API_KEY = "tavily_api_key"
CONTEXT_EXECUTION_ROLE_ARN = "execution_role_arn"  # Deprecated
CONTEXT_SECRET_ARN = "secret_arn"
CONTEXT_AGENT_NAME = "agent_name"
CONTEXT_MODEL_ID = "model_id"
CONTEXT_FALLBACK_MODEL_ID = "fallback_model_id"
CONTEXT_SOURCE_PATH = "source_path"
