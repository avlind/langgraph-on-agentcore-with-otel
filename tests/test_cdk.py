"""CDK assertion tests for infrastructure stacks."""

import os
import sys

import pytest
from aws_cdk import App
from aws_cdk.assertions import Match, Template

# Add cdk directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cdk"))

from stacks.iam_stack import IamPolicyStack
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


class TestIamPolicyStack:
    """Tests for the IamPolicyStack CDK stack."""

    VALID_ROLE_ARN = "arn:aws:iam::123456789012:role/TestRole"
    VALID_SECRET_ARN = "arn:aws:secretsmanager:us-east-2:123456789012:secret:test-secret-abc123"

    @pytest.fixture
    def template(self):
        """Create a template from IamPolicyStack."""
        app = App()
        stack = IamPolicyStack(
            app,
            "TestIamPolicyStack",
            execution_role_arn=self.VALID_ROLE_ARN,
            secret_arn=self.VALID_SECRET_ARN,
        )
        return Template.from_stack(stack)

    def test_policy_created(self, template):
        """Test that an IAM policy is created."""
        template.resource_count_is("AWS::IAM::Policy", 1)

    def test_policy_has_correct_name(self, template):
        """Test that the policy has the correct name."""
        template.has_resource_properties(
            "AWS::IAM::Policy",
            {"PolicyName": "SecretsManagerAccess"},
        )

    def test_policy_grants_get_secret_value(self, template):
        """Test that policy allows secretsmanager:GetSecretValue."""
        template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Action": "secretsmanager:GetSecretValue",
                                    "Effect": "Allow",
                                }
                            )
                        ]
                    )
                }
            },
        )

    def test_policy_uses_exact_secret_arn(self, template):
        """Test that policy uses exact secret ARN (no wildcard) for least privilege."""
        template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": {
                    "Statement": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Resource": self.VALID_SECRET_ARN,
                                }
                            )
                        ]
                    )
                }
            },
        )

    def test_output_exists(self, template):
        """Test that PolicyName output is defined."""
        template.has_output("PolicyName", {})

    def test_empty_role_arn_raises_error(self):
        """Test that empty execution_role_arn raises ValueError."""
        app = App()
        with pytest.raises(ValueError, match="execution_role_arn cannot be empty"):
            IamPolicyStack(
                app,
                "TestStack",
                execution_role_arn="",
                secret_arn=self.VALID_SECRET_ARN,
            )

    def test_invalid_role_arn_format_raises_error(self):
        """Test that invalid role ARN format raises ValueError."""
        app = App()
        with pytest.raises(ValueError, match="Invalid IAM role ARN format"):
            IamPolicyStack(
                app,
                "TestStack",
                execution_role_arn="invalid-arn",
                secret_arn=self.VALID_SECRET_ARN,
            )

    def test_empty_secret_arn_raises_error(self):
        """Test that empty secret_arn raises ValueError."""
        app = App()
        with pytest.raises(ValueError, match="secret_arn cannot be empty"):
            IamPolicyStack(
                app,
                "TestStack",
                execution_role_arn=self.VALID_ROLE_ARN,
                secret_arn="",
            )

    def test_invalid_secret_arn_format_raises_error(self):
        """Test that invalid secret ARN format raises ValueError."""
        app = App()
        with pytest.raises(ValueError, match="Invalid Secrets Manager ARN format"):
            IamPolicyStack(
                app,
                "TestStack",
                execution_role_arn=self.VALID_ROLE_ARN,
                secret_arn="invalid-arn",
            )
