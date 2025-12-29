"""Constants used across CDK stacks."""

# Stack names - used in deploy.sh and destroy.sh
SECRETS_STACK_NAME = "SecretsStack"
IAM_POLICY_STACK_NAME = "IamPolicyStack"

# Resource identifiers
SECRETS_MANAGER_POLICY_NAME = "SecretsManagerAccess"

# CDK context keys - passed via --context flags from deploy.sh
CONTEXT_SECRET_NAME = "secret_name"
CONTEXT_TAVILY_API_KEY = "tavily_api_key"
CONTEXT_EXECUTION_ROLE_ARN = "execution_role_arn"
CONTEXT_SECRET_ARN = "secret_arn"
