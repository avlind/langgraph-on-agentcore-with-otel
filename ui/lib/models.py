"""Data models for the UI application."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class InvocationStatus(Enum):
    """Status of an agent invocation."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class Prompt:
    """A saved prompt in the library."""

    id: str
    name: str
    text: str
    category: str = "general"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @classmethod
    def create(cls, name: str, text: str, category: str = "general") -> "Prompt":
        """Create a new prompt with a generated UUID."""
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            text=text,
            category=category,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "id": self.id,
            "name": self.name,
            "text": self.text,
            "category": self.category,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Prompt":
        """Deserialize from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            text=data["text"],
            category=data.get("category", "general"),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


@dataclass
class InvocationResult:
    """Result of a single agent invocation."""

    prompt_id: str
    prompt_name: str
    prompt_text: str
    status: InvocationStatus = InvocationStatus.PENDING
    result: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    session_id: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Calculate duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def duration_display(self) -> str:
        """Format duration for display."""
        duration = self.duration_seconds
        if duration is None:
            return "-"
        return f"{duration:.1f}s"


@dataclass
class AppConfig:
    """Application configuration."""

    aws_profile: str = "default"
    max_concurrent: int = 3
    timeout_seconds: int = 120
