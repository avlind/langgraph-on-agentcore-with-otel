"""CDK assertion tests for infrastructure stacks."""

import os
import sys

import pytest

# Skip all tests in this module if aws_cdk is not installed
# (aws_cdk is in the optional 'deploy' dependencies)
try:
    from aws_cdk import App, Environment
    from aws_cdk.assertions import Match, Template

    HAS_CDK = True
except ImportError:
    HAS_CDK = False

pytestmark = pytest.mark.skipif(
    not HAS_CDK, reason="aws_cdk not installed (use 'uv sync --extra deploy')"
)

if HAS_CDK:
    # Add cdk directory to path for imports
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cdk"))

    from stacks.agent_infra_stack import AgentInfraStack
    from stacks.memory_stack import MemoryStack
    from stacks.runtime_stack import RuntimeStack
    from stacks.secrets_stack import SecretsStack


class TestSecretsStack:
    """Tests for the SecretsStack CDK stack."""

    @pytest.fixture
    def template(self):
        """Create a template from SecretsStack."""
        app = App()
        stack = SecretsStack(
            app,
            "TestSecretsStack",
            secret_name="test-secret-name",
            tavily_api_key="test-api-key-value",
        )
        return Template.from_stack(stack)

    def test_secret_created(self, template):
        """Test that a Secrets Manager secret is created."""
        template.resource_count_is("AWS::SecretsManager::Secret", 1)

    def test_secret_has_correct_name(self, template):
        """Test that the secret has the correct name."""
        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {"Name": "test-secret-name"},
        )

    def test_secret_has_description(self, template):
        """Test that the secret has a description."""
        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {"Description": Match.string_like_regexp("Tavily.*")},
        )

    def test_outputs_exist(self, template):
        """Test that required outputs are defined."""
        template.has_output("SecretArn", {})
        template.has_output("SecretName", {})

    def test_empty_secret_name_raises_error(self):
        """Test that empty secret_name raises ValueError."""
        app = App()
        with pytest.raises(ValueError, match="secret_name cannot be empty"):
            SecretsStack(
                app,
                "TestStack",
                secret_name="",
                tavily_api_key="test-key",
            )

    def test_empty_api_key_raises_error(self):
        """Test that empty tavily_api_key raises ValueError."""
        app = App()
        with pytest.raises(ValueError, match="tavily_api_key cannot be empty"):
            SecretsStack(
                app,
                "TestStack",
                secret_name="test-secret",
                tavily_api_key="",
            )

    def test_whitespace_only_secret_name_raises_error(self):
        """Test that whitespace-only secret_name raises ValueError."""
        app = App()
        with pytest.raises(ValueError, match="secret_name cannot be empty"):
            SecretsStack(
                app,
                "TestStack",
                secret_name="   ",
                tavily_api_key="test-key",
            )


class TestAgentInfraStack:
    """Tests for the AgentInfraStack CDK stack."""

    @pytest.fixture
    def template(self, tmp_path):
        """Create a template from AgentInfraStack."""
        # Create a minimal source directory with required files
        (tmp_path / "langgraph_agent_web_search.py").write_text("# agent code")
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")
        (tmp_path / "Dockerfile").write_text("FROM python:3.13")

        app = App()
        stack = AgentInfraStack(
            app,
            "TestAgentInfraStack",
            secret_name="test-secret",
            agent_name="test-agent",
            model_id="anthropic.claude-haiku",
            fallback_model_id="anthropic.claude-sonnet",
            source_path=str(tmp_path),
            env=Environment(account="123456789012", region="us-east-2"),
        )
        return Template.from_stack(stack)

    def test_ecr_repository_created(self, template):
        """Test that an ECR repository is created."""
        template.resource_count_is("AWS::ECR::Repository", 1)

    def test_ecr_repository_has_correct_name(self, template):
        """Test that ECR repository has normalized name."""
        template.has_resource_properties(
            "AWS::ECR::Repository",
            {"RepositoryName": "agentcore-test-agent"},
        )

    def test_ecr_has_image_scanning_enabled(self, template):
        """Test that ECR repository has image scanning enabled."""
        template.has_resource_properties(
            "AWS::ECR::Repository",
            {"ImageScanningConfiguration": {"ScanOnPush": True}},
        )

    def test_codebuild_project_created(self, template):
        """Test that a CodeBuild project is created."""
        template.resource_count_is("AWS::CodeBuild::Project", 1)

    def test_codebuild_project_has_correct_name(self, template):
        """Test that CodeBuild project has correct name."""
        template.has_resource_properties(
            "AWS::CodeBuild::Project",
            {"Name": "test-agent-builder"},
        )

    def test_codebuild_has_privileged_mode(self, template):
        """Test that CodeBuild has privileged mode for Docker builds."""
        template.has_resource_properties(
            "AWS::CodeBuild::Project",
            {"Environment": Match.object_like({"PrivilegedMode": True})},
        )

    def test_execution_role_created(self, template):
        """Test that an execution role is created."""
        # Should have at least 2 roles: CodeBuild role and Execution role
        template.resource_count_is("AWS::IAM::Role", 2)

    def test_execution_role_has_correct_name(self, template):
        """Test that execution role has correct name."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {"RoleName": "AgentCore-test-agent-ExecutionRole"},
        )

    def test_execution_role_trusts_agentcore(self, template):
        """Test that execution role trusts bedrock-agentcore service."""
        template.has_resource_properties(
            "AWS::IAM::Role",
            {
                "AssumeRolePolicyDocument": Match.object_like(
                    {
                        "Statement": Match.array_with(
                            [
                                Match.object_like(
                                    {
                                        "Principal": {
                                            "Service": "bedrock-agentcore.amazonaws.com"
                                        }
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )

    def test_vpc_created(self, template):
        """Test that a VPC is created."""
        template.resource_count_is("AWS::EC2::VPC", 1)

    def test_nat_gateway_created(self, template):
        """Test that a NAT gateway is created."""
        template.resource_count_is("AWS::EC2::NatGateway", 1)

    def test_security_group_created(self, template):
        """Test that a security group is created for the agent."""
        template.has_resource_properties(
            "AWS::EC2::SecurityGroup",
            {
                "GroupDescription": "Security group for AgentCore runtime container",
            },
        )

    def test_execution_role_has_eni_permissions(self, template):
        """Test that execution role has ENI permissions for VPC networking."""
        template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": Match.object_like(
                    {
                        "Statement": Match.array_with(
                            [
                                Match.object_like(
                                    {
                                        "Action": Match.array_with(
                                            ["ec2:CreateNetworkInterface"]
                                        ),
                                        "Effect": "Allow",
                                    }
                                )
                            ]
                        )
                    }
                )
            },
        )

    def test_outputs_exist(self, template):
        """Test that required outputs are defined."""
        template.has_output("ECRRepositoryUri", {})
        template.has_output("CodeBuildProjectName", {})
        template.has_output("ExecutionRoleArn", {})
        template.has_output("VpcId", {})
        template.has_output("SecurityGroupId", {})


class TestMemoryStack:
    """Tests for the MemoryStack CDK stack."""

    @pytest.fixture
    def template(self):
        """Create a template from MemoryStack."""
        app = App()
        stack = MemoryStack(
            app,
            "TestMemoryStack",
            agent_name="test-agent",
        )
        return Template.from_stack(stack)

    def test_memory_created(self, template):
        """Test that AgentCore Memory is created."""
        template.resource_count_is("AWS::BedrockAgentCore::Memory", 1)

    def test_memory_has_correct_name(self, template):
        """Test that Memory has correct name pattern."""
        template.has_resource_properties(
            "AWS::BedrockAgentCore::Memory",
            {"Name": "test_agent_memory"},
        )

    def test_memory_has_expiry_duration(self, template):
        """Test that Memory has event expiry duration set."""
        template.has_resource_properties(
            "AWS::BedrockAgentCore::Memory",
            {"EventExpiryDuration": 30},
        )

    def test_outputs_exist(self, template):
        """Test that required outputs are defined."""
        template.has_output("MemoryArn", {})
        template.has_output("MemoryName", {})

    def test_empty_agent_name_raises_error(self):
        """Test that empty agent_name raises ValueError."""
        app = App()
        with pytest.raises(ValueError, match="agent_name cannot be empty"):
            MemoryStack(
                app,
                "TestStack",
                agent_name="",
            )

    def test_whitespace_only_agent_name_raises_error(self):
        """Test that whitespace-only agent_name raises ValueError."""
        app = App()
        with pytest.raises(ValueError, match="agent_name cannot be empty"):
            MemoryStack(
                app,
                "TestStack",
                agent_name="   ",
            )


class TestRuntimeStack:
    """Tests for the RuntimeStack CDK stack."""

    @pytest.fixture
    def template(self):
        """Create a template from RuntimeStack."""
        app = App()
        stack = RuntimeStack(
            app,
            "TestRuntimeStack",
            agent_name="test-agent",
            model_id="anthropic.claude-haiku",
            fallback_model_id="anthropic.claude-sonnet",
            secret_name="test-secret",
            ecr_repository_uri="123456789012.dkr.ecr.us-east-2.amazonaws.com/test-repo",
            execution_role_arn="arn:aws:iam::123456789012:role/TestExecutionRole",
            subnet_ids=["subnet-abc123", "subnet-def456"],
            security_group_ids=["sg-abc123"],
            env=Environment(account="123456789012", region="us-east-2"),
        )
        return Template.from_stack(stack)

    def test_runtime_created(self, template):
        """Test that AgentCore Runtime is created."""
        template.resource_count_is("AWS::BedrockAgentCore::Runtime", 1)

    def test_runtime_has_correct_name(self, template):
        """Test that Runtime has correct name."""
        template.has_resource_properties(
            "AWS::BedrockAgentCore::Runtime",
            {"AgentRuntimeName": "test-agent"},
        )

    def test_runtime_has_container_config(self, template):
        """Test that Runtime has container configuration."""
        template.has_resource_properties(
            "AWS::BedrockAgentCore::Runtime",
            {
                "AgentRuntimeArtifact": Match.object_like(
                    {
                        "ContainerConfiguration": Match.object_like(
                            {"ContainerUri": Match.string_like_regexp(".*:latest")}
                        )
                    }
                )
            },
        )

    def test_runtime_has_environment_variables(self, template):
        """Test that Runtime has required environment variables."""
        template.has_resource_properties(
            "AWS::BedrockAgentCore::Runtime",
            {
                "EnvironmentVariables": Match.object_like(
                    {
                        "AWS_REGION": "us-east-2",
                        "SECRET_NAME": "test-secret",
                        "MODEL_ID": "anthropic.claude-haiku",
                        "FALLBACK_MODEL_ID": "anthropic.claude-sonnet",
                    }
                )
            },
        )

    def test_runtime_has_private_network_mode(self, template):
        """Test that Runtime has private network mode with VPC config."""
        template.has_resource_properties(
            "AWS::BedrockAgentCore::Runtime",
            {
                "NetworkConfiguration": Match.object_like(
                    {
                        "NetworkMode": "PRIVATE",
                        "NetworkModeConfig": Match.object_like(
                            {
                                "Subnets": ["subnet-abc123", "subnet-def456"],
                                "SecurityGroups": ["sg-abc123"],
                            }
                        ),
                    }
                )
            },
        )

    def test_runtime_has_http_protocol(self, template):
        """Test that Runtime uses HTTP protocol."""
        template.has_resource_properties(
            "AWS::BedrockAgentCore::Runtime",
            {"ProtocolConfiguration": "HTTP"},
        )

    def test_outputs_exist(self, template):
        """Test that required outputs are defined."""
        template.has_output("RuntimeArn", {})
        template.has_output("RuntimeId", {})
