"""CDK assertion tests for infrastructure stacks."""

import pytest
from aws_cdk import App
from aws_cdk.assertions import Match, Template

import sys
import os

# Add cdk directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cdk"))

from stacks.secrets_stack import SecretsStack
from stacks.iam_stack import IamPolicyStack


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

    def test_outputs_exist(self, template):
        """Test that required outputs are defined."""
        template.has_output("SecretArn", {})
        template.has_output("SecretName", {})


class TestIamPolicyStack:
    """Tests for the IamPolicyStack CDK stack."""

    @pytest.fixture
    def template(self):
        """Create a template from IamPolicyStack."""
        app = App()
        stack = IamPolicyStack(
            app,
            "TestIamPolicyStack",
            execution_role_arn="arn:aws:iam::123456789012:role/TestRole",
            secret_arn="arn:aws:secretsmanager:us-east-2:123456789012:secret:test-secret-abc123",
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
                                    "Resource": "arn:aws:secretsmanager:us-east-2:123456789012:secret:test-secret-abc123",
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
