"""Prompt library persistence using JSON file."""

import json
from pathlib import Path

from .models import Prompt


class PromptStore:
    """Manages prompt library persistence using JSON file."""

    def __init__(self, path: Path | None = None):
        self._path = path or Path(__file__).parent.parent / "prompts.json"
        self._prompts: dict[str, Prompt] = {}
        self._load()

    def _load(self) -> None:
        """Load prompts from JSON file."""
        if not self._path.exists():
            self._prompts = {}
            self._initialize_defaults()
            return

        try:
            with open(self._path) as f:
                data = json.load(f)

            prompts_data = data.get("prompts", [])
            self._prompts = {p["id"]: Prompt.from_dict(p) for p in prompts_data}
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error loading prompts: {e}")
            self._prompts = {}
            self._initialize_defaults()

    def _save(self) -> None:
        """Save prompts to JSON file."""
        data = {
            "version": "1.0",
            "prompts": [p.to_dict() for p in self._prompts.values()],
        }
        with open(self._path, "w") as f:
            json.dump(data, f, indent=2)

    def _initialize_defaults(self) -> None:
        """Initialize with default prompts if store is empty."""
        if self._prompts:
            return

        defaults = get_default_prompts()
        for prompt in defaults:
            self._prompts[prompt.id] = prompt
        self._save()

    def list_prompts(self) -> list[Prompt]:
        """Return all prompts sorted by name."""
        return sorted(self._prompts.values(), key=lambda p: p.name.lower())

    def get_prompt(self, prompt_id: str) -> Prompt | None:
        """Get a single prompt by ID."""
        return self._prompts.get(prompt_id)

    def add_prompt(self, prompt: Prompt) -> None:
        """Add or update a prompt."""
        self._prompts[prompt.id] = prompt
        self._save()

    def update_prompt(self, prompt_id: str, name: str, text: str, category: str) -> Prompt | None:
        """Update an existing prompt. Returns updated prompt or None if not found."""
        prompt = self._prompts.get(prompt_id)
        if not prompt:
            return None

        updated = Prompt(
            id=prompt_id,
            name=name,
            text=text,
            category=category,
            created_at=prompt.created_at,
        )
        self._prompts[prompt_id] = updated
        self._save()
        return updated

    def delete_prompt(self, prompt_id: str) -> bool:
        """Delete a prompt by ID. Returns True if deleted."""
        if prompt_id in self._prompts:
            del self._prompts[prompt_id]
            self._save()
            return True
        return False

    def search_prompts(self, query: str) -> list[Prompt]:
        """Search prompts by name or text."""
        query = query.lower()
        results = [
            p for p in self._prompts.values() if query in p.name.lower() or query in p.text.lower()
        ]
        return sorted(results, key=lambda p: p.name.lower())


def get_default_prompts() -> list[Prompt]:
    """Return a set of default prompts for initial setup."""
    defaults = [
        ("Weather Query", "What is the current weather in Seattle?", "general"),
        ("AWS News", "Search for the latest AWS news and announcements", "tech"),
        ("Stock Price", "What is the current stock price of Amazon?", "finance"),
        ("Python Tutorial", "Find a tutorial on Python async programming", "tech"),
        ("Tech News", "What are the top technology news stories today?", "tech"),
        ("Sports Scores", "What were the latest NBA game scores?", "sports"),
        ("Recipe Search", "Find a recipe for chocolate chip cookies", "lifestyle"),
        ("Travel Info", "What are the top tourist attractions in Tokyo?", "travel"),
        ("Science News", "Search for recent discoveries in astronomy", "science"),
        ("Book Recommendations", "What are the best programming books of 2024?", "tech"),
        ("Movie Reviews", "Find reviews for recent science fiction movies", "entertainment"),
        ("Health Tips", "Search for healthy breakfast ideas", "lifestyle"),
        ("Long Response Test", "Provide a detailed summary of machine learning concepts", "tech"),
        ("Simple Query", "What is 2 + 2?", "test"),
        ("Current Events", "What major events happened in the news today?", "general"),
    ]

    return [Prompt.create(name, text, category) for name, text, category in defaults]
