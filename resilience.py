"""
Resilience utilities for LLM invocations with retry and fallback logic.

This module provides:
- Error classification for Bedrock API errors
- ResilientLLMInvoker class for automatic retry with exponential backoff
  and fallback to a secondary model
"""

import logging

from botocore.exceptions import ClientError
from langchain_core.messages import BaseMessage
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# Error codes that should trigger retry on primary model
RETRYABLE_ERROR_CODES = {
    "ThrottlingException",
    "ServiceUnavailable",
    "InternalFailure",
    "ServiceException",
    "RequestTimeout",
}

# Error codes that should trigger immediate fallback (no retry)
FALLBACK_ERROR_CODES = {
    "ModelNotReadyException",
    "ModelStreamErrorException",
    "ModelTimeoutException",
    "ModelErrorException",
    "ServiceQuotaExceededException",  # Quota exhausted, fallback immediately
}


def is_retryable_error(exception: Exception) -> bool:
    """Check if exception should trigger a retry on the same model."""
    if isinstance(exception, ClientError):
        error_code = exception.response.get("Error", {}).get("Code", "")
        return error_code in RETRYABLE_ERROR_CODES
    return False


def should_fallback(exception: Exception) -> bool:
    """Check if exception should trigger fallback to secondary model."""
    if isinstance(exception, ClientError):
        error_code = exception.response.get("Error", {}).get("Code", "")
        return error_code in FALLBACK_ERROR_CODES
    return False


class ResilientLLMInvoker:
    """Wrapper that provides retry and fallback logic for LLM invocations."""

    def __init__(
        self,
        primary_llm_with_tools,
        fallback_llm_with_tools,
        max_retries: int = 3,
        min_wait_seconds: float = 1.0,
        max_wait_seconds: float = 10.0,
    ):
        self.primary_llm = primary_llm_with_tools
        self.fallback_llm = fallback_llm_with_tools
        self.max_retries = max_retries
        self.min_wait = min_wait_seconds
        self.max_wait = max_wait_seconds
        self._using_fallback = False

    def invoke(self, messages: list[BaseMessage]) -> BaseMessage:
        """
        Invoke LLM with retry and fallback logic.

        Flow:
        1. Try primary model
        2. On retryable error, retry up to max_retries times with exponential backoff
        3. After retries exhausted or on fallback-triggering error, use fallback model
        """
        self._using_fallback = False

        try:
            return self._invoke_with_retry(messages)
        except Exception as primary_error:
            logger.warning(
                "Primary model failed after retries: %s. Falling back to secondary model.",
                str(primary_error),
            )
            return self._invoke_fallback(messages, primary_error)

    def _invoke_with_retry(self, messages: list[BaseMessage]) -> BaseMessage:
        """Invoke primary model with retry logic."""

        @retry(
            retry=retry_if_exception(is_retryable_error),
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=self.min_wait, max=self.max_wait),
            reraise=True,
        )
        def _invoke():
            return self.primary_llm.invoke(messages)

        return _invoke()

    def _invoke_fallback(
        self, messages: list[BaseMessage], original_error: Exception
    ) -> BaseMessage:
        """Invoke fallback model."""
        self._using_fallback = True
        logger.info(
            "Using fallback model due to primary model failure: %s",
            str(original_error),
        )

        try:
            response = self.fallback_llm.invoke(messages)
            logger.info("Fallback model invocation successful")
            return response
        except Exception as fallback_error:
            logger.error(
                "Fallback model also failed: %s. Original error: %s",
                str(fallback_error),
                str(original_error),
            )
            raise RuntimeError(
                f"Both primary and fallback models failed. "
                f"Primary error: {original_error}. "
                f"Fallback error: {fallback_error}"
            ) from fallback_error

    @property
    def using_fallback(self) -> bool:
        """Returns True if the last invocation used the fallback model."""
        return self._using_fallback
