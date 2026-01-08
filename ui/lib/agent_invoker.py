"""Agent invocation wrapper with async execution support."""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import boto3
from botocore.exceptions import ClientError

from .models import AgentRuntime, AppConfig, InvocationResult, InvocationStatus


@dataclass
class InvocationTask:
    """A task to be executed."""

    prompt_id: str
    prompt_name: str
    prompt_text: str


class AgentInvoker:
    """
    Executes agent invocations using boto3 HTTP API.

    Uses asyncio.to_thread() for non-blocking execution within NiceGUI's
    async event loop. Manages concurrent execution with semaphore limiting.
    """

    def __init__(self, config: AppConfig):
        self._config = config
        self._semaphore: asyncio.Semaphore | None = None
        self._cancelled = False
        self._client = None

    def _get_client(self):
        """Get or create boto3 bedrock-agentcore client."""
        if self._client is None:
            if self._config.aws_profile:
                session = boto3.Session(profile_name=self._config.aws_profile)
            else:
                session = boto3.Session()
            self._client = session.client("bedrock-agentcore", region_name=self._config.aws_region)
        return self._client

    def _invoke_sync(self, prompt: str, session_id: str, agent: AgentRuntime) -> tuple[bool, str]:
        """
        Synchronous invocation via boto3 HTTP API.

        Uses invoke_agent_runtime to call the deployed agent.
        Returns: (success, result_or_error)
        """
        try:
            client = self._get_client()
            payload = json.dumps({"prompt": prompt}).encode("utf-8")

            response = client.invoke_agent_runtime(
                agentRuntimeArn=agent.arn,
                payload=payload,
            )

            # Read the streaming response body
            streaming_body = response.get("response")
            if streaming_body:
                response_data = streaming_body.read()
                try:
                    data = json.loads(response_data.decode("utf-8"))
                    if "result" in data:
                        return True, data["result"]
                    elif "error" in data:
                        return False, f"Agent error: {data['error']}"
                    else:
                        return True, response_data.decode("utf-8")
                except json.JSONDecodeError:
                    return True, response_data.decode("utf-8")
            else:
                return False, "No response body received"

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_msg = e.response.get("Error", {}).get("Message", str(e))
            return False, f"{error_code}: {error_msg}"
        except Exception as e:
            return False, str(e)

    def _get_session_id_from_logs(self, agent: AgentRuntime, start_time_ms: int) -> str | None:
        """
        Query CloudWatch Logs to get the session ID from log attributes.

        Args:
            agent: Agent runtime information
            start_time_ms: Timestamp in milliseconds to start searching from

        Returns:
            Session ID (from attributes.session.id) or None if not found
        """
        try:
            if self._config.aws_profile:
                session = boto3.Session(profile_name=self._config.aws_profile)
            else:
                session = boto3.Session()

            logs_client = session.client("logs", region_name=self._config.aws_region)
            log_group = f"/aws/bedrock-agentcore/runtimes/{agent.runtime_id}-DEFAULT"

            # Try up to 3 times with small delays (logs may not be immediately available)
            for attempt in range(3):
                if attempt > 0:
                    time.sleep(1)  # Wait 1 second between attempts

                try:
                    response = logs_client.filter_log_events(
                        logGroupName=log_group,
                        startTime=start_time_ms,
                        limit=100,  # Get recent events
                    )

                    # Parse events looking for session.id in attributes (most recent first)
                    events = response.get("events", [])
                    for event in reversed(events):
                        message = event.get("message", "")
                        try:
                            log_data = json.loads(message)
                            attributes = log_data.get("attributes", {})
                            session_id = attributes.get("session.id")
                            if session_id:
                                return session_id
                        except (json.JSONDecodeError, AttributeError, TypeError):
                            continue

                    # If we found events but no session ID yet, try again
                    if events:
                        continue

                except ClientError:
                    if attempt < 2:
                        continue
                    break

            return None

        except Exception as e:
            print(f"Error querying CloudWatch Logs for session ID: {e}")
            return None

    async def invoke_async(
        self,
        task: InvocationTask,
        on_status_change: Callable[[InvocationResult], None],
    ) -> InvocationResult:
        """
        Execute a single invocation asynchronously.

        Uses asyncio.to_thread() to run blocking boto3 call in thread pool.
        Calls on_status_change callback when status changes (for UI updates).
        """
        # Initialize semaphore lazily (needs running event loop)
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._config.max_concurrent)

        # Generate temporary session ID (will be replaced with actual trace ID)
        temp_session_id = str(uuid.uuid4())

        result = InvocationResult(
            prompt_id=task.prompt_id,
            prompt_name=task.prompt_name,
            prompt_text=task.prompt_text,
            status=InvocationStatus.PENDING,
            session_id=temp_session_id,
            agent=self._config.selected_agent,
        )
        on_status_change(result)

        # Check if agent is selected
        if self._config.selected_agent is None:
            result.status = InvocationStatus.ERROR
            result.error_message = "No agent selected. Please select an agent first."
            on_status_change(result)
            return result

        # Check if cancelled before acquiring semaphore
        if self._cancelled:
            result.status = InvocationStatus.ERROR
            result.error_message = "Cancelled"
            on_status_change(result)
            return result

        async with self._semaphore:
            # Check again after acquiring semaphore
            if self._cancelled:
                result.status = InvocationStatus.ERROR
                result.error_message = "Cancelled"
                on_status_change(result)
                return result

            result.status = InvocationStatus.RUNNING
            result.started_at = datetime.now()
            start_time_ms = int(result.started_at.timestamp() * 1000)
            on_status_change(result)

            success, output = await asyncio.to_thread(
                self._invoke_sync,
                task.prompt_text,
                temp_session_id,
                self._config.selected_agent,
            )

            result.completed_at = datetime.now()

            if success:
                result.status = InvocationStatus.SUCCESS
                result.result = output

                # Get actual session ID from CloudWatch Logs
                session_id = await asyncio.to_thread(
                    self._get_session_id_from_logs,
                    self._config.selected_agent,
                    start_time_ms,
                )

                # Update session_id with actual session ID if found
                if session_id:
                    result.session_id = session_id
                else:
                    # Keep temporary UUID if session ID not found
                    print("Warning: Could not retrieve session ID from logs, using temporary ID")
            else:
                if "Timeout" in output:
                    result.status = InvocationStatus.TIMEOUT
                else:
                    result.status = InvocationStatus.ERROR
                result.error_message = output

            on_status_change(result)
            return result

    async def invoke_batch(
        self,
        tasks: list[InvocationTask],
        on_status_change: Callable[[InvocationResult], None],
    ) -> list[InvocationResult]:
        """
        Execute multiple invocations concurrently.

        Uses asyncio.gather() to run all tasks, respecting the semaphore limit.
        """
        self._cancelled = False

        coroutines = [self.invoke_async(task, on_status_change) for task in tasks]
        return await asyncio.gather(*coroutines)

    def cancel(self) -> None:
        """Cancel pending invocations."""
        self._cancelled = True

    def update_config(self, config: AppConfig) -> None:
        """Update configuration. Recreates client/semaphore on next invocation."""
        self._config = config
        self._semaphore = None  # Will be recreated with new max_concurrent
        self._client = None  # Will be recreated with new profile/region
