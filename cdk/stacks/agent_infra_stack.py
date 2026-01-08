"""
CDK stack for AgentCore infrastructure.

This stack creates the infrastructure needed to deploy a LangGraph agent to
AWS Bedrock AgentCore, including:
- ECR repository for the agent container
- CodeBuild project to build the Docker image
- IAM execution role with required permissions

The AgentCore Memory is created in a separate MemoryStack (for parallel deployment).
The AgentCore Runtime is created in a separate RuntimeStack after CodeBuild
has pushed the Docker image (since Runtime validation requires the image to exist).

Usage:
    cdk deploy AgentInfraStack \\
        --context secret_name="langgraph-agent/tavily-api-key" \\
        --context agent_name="langgraph-search-agent" \\
        --context model_id="..." \\
        --context fallback_model_id="..."
"""

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_codebuild as codebuild,
)
from aws_cdk import (
    aws_ecr as ecr,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_s3_assets as s3_assets,
)
from constructs import Construct


class AgentInfraStack(Stack):
    """
    Stack for AgentCore infrastructure (ECR, CodeBuild, IAM).

    This stack creates build infrastructure. Memory is in MemoryStack (for parallel
    deployment with CodeBuild). Runtime is in RuntimeStack (needs image to exist).
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        secret_name: str,
        agent_name: str,
        model_id: str,
        fallback_model_id: str,
        source_path: str,
        **kwargs,
    ) -> None:
        """
        Initialize the AgentInfraStack.

        Args:
            scope: CDK app or stage scope.
            construct_id: Unique identifier for this stack.
            secret_name: Name of the secret (for environment variable).
            agent_name: Name for the AgentCore runtime.
            model_id: Primary Bedrock model ID.
            fallback_model_id: Fallback Bedrock model ID.
            source_path: Path to the source code directory.
            **kwargs: Additional stack properties.
        """
        super().__init__(scope, construct_id, **kwargs)

        # Normalize agent name for ECR (lowercase, no special chars)
        ecr_repo_name = f"agentcore-{agent_name}".lower().replace("_", "-")

        # 1. ECR Repository
        ecr_repo = ecr.Repository(
            self,
            "AgentECR",
            repository_name=ecr_repo_name,
            removal_policy=RemovalPolicy.DESTROY,
            empty_on_delete=True,
            image_scan_on_push=True,
            image_tag_mutability=ecr.TagMutability.MUTABLE,
        )

        # 2. Upload source code as S3 asset for CodeBuild
        # Use .dockerignore-style patterns to exclude unnecessary files
        source_asset = s3_assets.Asset(
            self,
            "SourceAsset",
            path=source_path,
            exclude=[
                # Git
                ".git",
                ".gitignore",
                ".gitattributes",
                # Python
                ".venv",
                "venv",
                "__pycache__",
                "*.pyc",
                "*.pyo",
                "*.egg-info",
                ".Python",
                # Environment
                ".env",
                "*.log",
                # CDK (critical - prevents recursive copy)
                "cdk",
                "cdk.out",
                # AgentCore generated files
                ".bedrock_agentcore",
                ".bedrock_agentcore.yaml",
                # Documentation and tests
                "docs",
                "tests",
                ".pytest_cache",
                # Scripts (not needed in container)
                "scripts",
                # IDE
                ".vscode",
                ".idea",
                # Other
                ".DS_Store",
                "*.md",
                ".claude",
            ],
        )

        # 3. CodeBuild IAM Role
        codebuild_role = iam.Role(
            self,
            "CodeBuildRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
            description="Role for CodeBuild to build agent container",
        )

        # Grant CodeBuild permissions
        ecr_repo.grant_pull_push(codebuild_role)
        source_asset.grant_read(codebuild_role)

        codebuild_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=["*"],
            )
        )

        # 4. CodeBuild Project
        build_project = codebuild.Project(
            self,
            "AgentBuilder",
            project_name=f"{agent_name}-builder",
            description=f"Build Docker image for {agent_name} agent",
            source=codebuild.Source.s3(
                bucket=source_asset.bucket,
                path=source_asset.s3_object_key,
            ),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxArmBuildImage.AMAZON_LINUX_2_STANDARD_3_0,
                privileged=True,  # Required for Docker builds
                compute_type=codebuild.ComputeType.SMALL,
            ),
            environment_variables={
                "AWS_ACCOUNT_ID": codebuild.BuildEnvironmentVariable(value=self.account),
                "AWS_REGION": codebuild.BuildEnvironmentVariable(value=self.region),
                "ECR_REPO_URI": codebuild.BuildEnvironmentVariable(value=ecr_repo.repository_uri),
                "IMAGE_TAG": codebuild.BuildEnvironmentVariable(value="latest"),
            },
            build_spec=codebuild.BuildSpec.from_object(
                {
                    "version": "0.2",
                    "phases": {
                        "pre_build": {
                            "commands": [
                                "echo Logging in to Amazon ECR...",
                                # ECR login command
                                "aws ecr get-login-password --region $AWS_REGION"
                                " | docker login --username AWS --password-stdin"
                                " $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com",
                            ]
                        },
                        "build": {
                            "commands": [
                                "echo Building Docker image...",
                                "docker build --platform linux/arm64 -t $ECR_REPO_URI:$IMAGE_TAG .",
                            ]
                        },
                        "post_build": {
                            "commands": [
                                "echo Pushing Docker image...",
                                "docker push $ECR_REPO_URI:$IMAGE_TAG",
                                "echo Build completed successfully",
                            ]
                        },
                    },
                }
            ),
            role=codebuild_role,
            timeout=Duration.minutes(30),
        )

        # 5. AgentCore Execution Role
        execution_role = iam.Role(
            self,
            "ExecutionRole",
            role_name=f"AgentCore-{agent_name}-ExecutionRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description=f"Execution role for AgentCore runtime {agent_name}",
        )

        # Grant Secrets Manager access (wildcard to allow parallel stack deployment)
        execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="SecretsManagerAccess",
                actions=["secretsmanager:GetSecretValue"],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:{secret_name}*"
                ],
            )
        )

        # Grant Bedrock model invocation
        # Note: global.* model IDs create ARNs without a region (arn:aws:bedrock:::...)
        # so we use * for region to match all cases including empty region
        execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockModelAccess",
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=[
                    "arn:aws:bedrock:*::foundation-model/*",
                    f"arn:aws:bedrock:*:{self.account}:inference-profile/*",
                ],
            )
        )

        # Grant ECR pull access
        execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="ECRAccess",
                actions=[
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                ],
                resources=["*"],
            )
        )

        # Grant CloudWatch Logs access
        execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="CloudWatchLogsAccess",
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=["*"],
            )
        )

        # Grant X-Ray access for OpenTelemetry trace export
        execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="XRayAccess",
                actions=[
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                ],
                resources=["*"],
            )
        )

        # Outputs - for visibility (RuntimeStack uses cross-stack references directly)
        CfnOutput(
            self,
            "ECRRepositoryUri",
            value=ecr_repo.repository_uri,
            description="ECR repository URI for agent container",
        )

        CfnOutput(
            self,
            "CodeBuildProjectName",
            value=build_project.project_name,
            description="CodeBuild project name for building agent container",
        )

        CfnOutput(
            self,
            "ExecutionRoleArn",
            value=execution_role.role_arn,
            description="IAM execution role ARN for AgentCore runtime",
        )

        # Store references for cross-stack usage
        self.ecr_repo = ecr_repo
        self.build_project = build_project
        self.execution_role = execution_role
