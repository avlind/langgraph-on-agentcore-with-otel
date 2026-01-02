"""Agent invocation wrapper with async execution support."""

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .models import AppConfig, InvocationResult, InvocationStatus


@dataclass
class InvocationTask:
    """A task to be executed."""

    prompt_id: str
    prompt_name: str
    prompt_text: str


class AgentInvoker:
    """
    Executes agent invocations using subprocess calls to agentcore CLI.

    Uses asyncio.to_thread() for non-blocking execution within NiceGUI's
    async event loop. Manages concurrent execution with semaphore limiting.
    """

    def __init__(self, config: AppConfig):
        self._config = config
        self._semaphore: asyncio.Semaphore | None = None
        self._cancelled = False

    def _invoke_sync(self, prompt: str) -> tuple[bool, str]:
        """
        Synchronous subprocess call to agentcore invoke.

        Runs: AWS_PROFILE={profile} agentcore invoke '{"prompt": "..."}'
        Returns: (success, result_or_error)
        """
        payload = json.dumps({"prompt": prompt})
        cmd = ["uv", "run", "agentcore", "invoke", payload]

        env = os.environ.copy()
        if self._config.aws_profile:
            env["AWS_PROFILE"] = self._config.aws_profile

        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=self._config.timeout_seconds,
            )

            if result.returncode == 0:
                # Try to parse JSON response
                try:
                    response = json.loads(result.stdout)
                    return True, response.get("result", result.stdout)
                except json.JSONDecodeError:
                    # Return raw stdout if not JSON
                    return True, result.stdout.strip()
            else:
                error = result.stderr.strip() or result.stdout.strip() or "Unknown error"
                return False, error

        except subprocess.TimeoutExpired:
            return False, f"Timeout after {self._config.timeout_seconds}s"
        except FileNotFoundError:
            return False, "uv or agentcore not found. Run: uv sync --extra deploy"
        except Exception as e:
            return False, str(e)

    async def invoke_async(
        self,
        task: InvocationTask,
        on_status_change: Callable[[InvocationResult], None],
    ) -> InvocationResult:
        """
        Execute a single invocation asynchronously.

        Uses asyncio.to_thread() to run blocking subprocess in thread pool.
        Calls on_status_change callback when status changes (for UI updates).
        """
        # Initialize semaphore lazily (needs running event loop)
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._config.max_concurrent)

        result = InvocationResult(
            prompt_id=task.prompt_id,
            prompt_name=task.prompt_name,
            prompt_text=task.prompt_text,
            status=InvocationStatus.PENDING,
        )
        on_status_change(result)

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
            on_status_change(result)

            success, output = await asyncio.to_thread(self._invoke_sync, task.prompt_text)

            result.completed_at = datetime.now()

            if success:
                result.status = InvocationStatus.SUCCESS
                result.result = output
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
        """Update configuration. Recreates semaphore on next invocation."""
        self._config = config
        self._semaphore = None  # Will be recreated with new max_concurrent
