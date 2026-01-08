"""AWS client helpers for boto3 operations."""

import boto3
from botocore.exceptions import ClientError

from .console import print_success, print_warning


def get_session(profile: str | None = None) -> boto3.Session:
    """Create boto3 session with optional profile."""
    if profile:
        return boto3.Session(profile_name=profile)
    return boto3.Session()


def get_account_id(session: boto3.Session) -> str:
    """Get the AWS account ID."""
    sts = session.client("sts")
    return sts.get_caller_identity()["Account"]


def check_cdk_bootstrap(session: boto3.Session, region: str) -> bool:
    """Check if CDK is bootstrapped in the account/region."""
    cf = session.client("cloudformation", region_name=region)
    try:
        cf.describe_stacks(StackName="CDKToolkit")
        return True
    except ClientError as e:
        if "does not exist" in str(e):
            return False
        raise


def stack_exists(session: boto3.Session, stack_name: str, region: str) -> bool:
    """Check if a CloudFormation stack exists."""
    cf = session.client("cloudformation", region_name=region)
    try:
        cf.describe_stacks(StackName=stack_name)
        return True
    except ClientError as e:
        if "does not exist" in str(e):
            return False
        raise


def get_stack_output(
    session: boto3.Session, stack_name: str, output_key: str, region: str
) -> str | None:
    """Get a specific output from a CloudFormation stack."""
    cf = session.client("cloudformation", region_name=region)
    try:
        response = cf.describe_stacks(StackName=stack_name)
        stacks = response.get("Stacks", [])
        if not stacks:
            return None

        outputs = stacks[0].get("Outputs", [])
        for output in outputs:
            if output.get("OutputKey") == output_key:
                return output.get("OutputValue")
        return None
    except ClientError:
        return None


def delete_stack_and_wait(session: boto3.Session, stack_name: str, region: str) -> bool:
    """Delete a CloudFormation stack and wait for completion."""
    cf = session.client("cloudformation", region_name=region)

    if not stack_exists(session, stack_name, region):
        print_warning(f"{stack_name} not found, skipping")
        return False

    cf.delete_stack(StackName=stack_name)

    # Wait for deletion
    waiter = cf.get_waiter("stack_delete_complete")
    try:
        waiter.wait(StackName=stack_name)
        print_success(f"{stack_name} destroyed")
        return True
    except Exception:
        # Stack may already be deleted
        return True


def delete_secret(session: boto3.Session, secret_id: str, region: str, force: bool = True) -> bool:
    """Delete a Secrets Manager secret."""
    sm = session.client("secretsmanager", region_name=region)

    try:
        sm.describe_secret(SecretId=secret_id)
    except ClientError as e:
        if "ResourceNotFoundException" in str(e):
            print_warning("Secret not found, skipping")
            return False
        raise

    if force:
        sm.delete_secret(SecretId=secret_id, ForceDeleteWithoutRecovery=True)
    else:
        sm.delete_secret(SecretId=secret_id)

    print_success(f"Secret deleted: {secret_id}")
    return True


def delete_ecr_repository(
    session: boto3.Session, repo_name: str, region: str, force: bool = True
) -> bool:
    """Delete an ECR repository."""
    ecr = session.client("ecr", region_name=region)

    try:
        ecr.describe_repositories(repositoryNames=[repo_name])
    except ClientError as e:
        if "RepositoryNotFoundException" in str(e):
            print_warning("ECR repository not found, skipping")
            return False
        raise

    ecr.delete_repository(repositoryName=repo_name, force=force)
    print_success(f"ECR repository deleted: {repo_name}")
    return True
