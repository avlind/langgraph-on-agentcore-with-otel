"""Prompt library UI component."""

from nicegui import ui

from ..lib.models import Prompt
from ..lib.prompt_store import PromptStore


class PromptLibrary:
    """UI component for managing the prompt library."""

    def __init__(self, store: PromptStore, on_selection_change: callable):
        self.store = store
        self.on_selection_change = on_selection_change
        self.selected_ids: set[str] = set()
        self.search_query = ""
        self._prompt_container = None
        self._selection_label = None

    def render(self) -> None:
        """Render the prompt library panel."""
        with ui.card().classes("w-full"):
            ui.label("Prompt Library").classes("text-lg font-bold mb-2")

            # Search input
            ui.input(
                placeholder="Search prompts...",
                on_change=lambda e: self._on_search(e.value),
            ).classes("w-full mb-2")

            # Selection info
            self._selection_label = ui.label("0 selected").classes("text-sm text-gray-500 mb-2")

            # Prompt list container
            self._prompt_container = ui.column().classes("w-full max-h-96 overflow-y-auto")
            self._render_prompts()

            # Action buttons
            with ui.row().classes("w-full mt-2 gap-2"):
                ui.button("Add", on_click=self._show_add_dialog, icon="add").props("dense")
                ui.button("Delete", on_click=self._confirm_delete, icon="delete").props(
                    "dense color=negative"
                )

            # Select all / none buttons
            with ui.row().classes("w-full mt-1 gap-2"):
                ui.button("Select All", on_click=self._select_all).props("dense flat size=sm")
                ui.button("Select None", on_click=self._select_none).props("dense flat size=sm")

    def _render_prompts(self) -> None:
        """Render the list of prompts."""
        self._prompt_container.clear()

        prompts = (
            self.store.search_prompts(self.search_query)
            if self.search_query
            else self.store.list_prompts()
        )

        with self._prompt_container:
            if not prompts:
                ui.label("No prompts found").classes("text-gray-400 italic")
                return

            for prompt in prompts:
                self._render_prompt_item(prompt)

    def _render_prompt_item(self, prompt: Prompt) -> None:
        """Render a single prompt item with checkbox and edit button."""
        is_selected = prompt.id in self.selected_ids

        with ui.row().classes("w-full items-center gap-2 p-1 hover:bg-gray-100 rounded"):
            ui.checkbox(
                value=is_selected,
                on_change=lambda e, p=prompt: self._toggle_selection(p.id, e.value),
            )
            with ui.column().classes("flex-grow min-w-0"):
                ui.label(prompt.name).classes("font-medium text-sm")
                preview = prompt.text[:60] + "..." if len(prompt.text) > 60 else prompt.text
                ui.label(preview).classes("text-xs text-gray-500 truncate")
            ui.badge(prompt.category).props("outline").classes("text-xs")
            ui.button(
                icon="edit",
                on_click=lambda p=prompt: self._edit_prompt(p.id),
            ).props("flat dense round size=sm").classes("opacity-50 hover:opacity-100")

    def _toggle_selection(self, prompt_id: str, selected: bool) -> None:
        """Toggle selection of a prompt."""
        if selected:
            self.selected_ids.add(prompt_id)
        else:
            self.selected_ids.discard(prompt_id)
        self._update_selection_label()
        self.on_selection_change(self.get_selected_prompts())

    def _update_selection_label(self) -> None:
        """Update the selection count label."""
        count = len(self.selected_ids)
        self._selection_label.text = f"{count} selected"

    def _on_search(self, query: str) -> None:
        """Handle search input change."""
        self.search_query = query
        self._render_prompts()

    def _select_all(self) -> None:
        """Select all visible prompts."""
        prompts = (
            self.store.search_prompts(self.search_query)
            if self.search_query
            else self.store.list_prompts()
        )
        self.selected_ids = {p.id for p in prompts}
        self._render_prompts()
        self._update_selection_label()
        self.on_selection_change(self.get_selected_prompts())

    def _select_none(self) -> None:
        """Deselect all prompts."""
        self.selected_ids.clear()
        self._render_prompts()
        self._update_selection_label()
        self.on_selection_change(self.get_selected_prompts())

    def get_selected_prompts(self) -> list[Prompt]:
        """Get list of selected prompts."""
        return [p for p in self.store.list_prompts() if p.id in self.selected_ids]

    def _show_add_dialog(self) -> None:
        """Show dialog to add a new prompt."""
        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label("Add New Prompt").classes("text-lg font-bold mb-2")

            name_input = ui.input("Name", placeholder="My Prompt").classes("w-full")
            text_input = ui.textarea("Prompt Text", placeholder="Enter your prompt...").classes(
                "w-full"
            )
            category_input = ui.input("Category", value="general").classes("w-full")

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                def save():
                    if name_input.value and text_input.value:
                        prompt = Prompt.create(
                            name=name_input.value,
                            text=text_input.value,
                            category=category_input.value or "general",
                        )
                        self.store.add_prompt(prompt)
                        self._render_prompts()
                        dialog.close()
                        ui.notify(f"Added prompt: {prompt.name}", type="positive")

                ui.button("Save", on_click=save).props("color=primary")

        dialog.open()

    def _edit_prompt(self, prompt_id: str) -> None:
        """Show dialog to edit a specific prompt."""
        prompt = self.store.get_prompt(prompt_id)
        if not prompt:
            return

        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label("Edit Prompt").classes("text-lg font-bold mb-2")

            name_input = ui.input("Name", value=prompt.name).classes("w-full")
            text_input = ui.textarea("Prompt Text", value=prompt.text).classes("w-full")
            category_input = ui.input("Category", value=prompt.category).classes("w-full")

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                def save():
                    if name_input.value and text_input.value:
                        self.store.update_prompt(
                            prompt_id=prompt_id,
                            name=name_input.value,
                            text=text_input.value,
                            category=category_input.value or "general",
                        )
                        self._render_prompts()
                        dialog.close()
                        ui.notify(f"Updated prompt: {name_input.value}", type="positive")

                ui.button("Save", on_click=save).props("color=primary")

        dialog.open()

    def _confirm_delete(self) -> None:
        """Confirm and delete selected prompts."""
        if not self.selected_ids:
            ui.notify("No prompts selected", type="warning")
            return

        count = len(self.selected_ids)

        with ui.dialog() as dialog, ui.card():
            ui.label(f"Delete {count} prompt(s)?").classes("text-lg font-bold")
            ui.label("This action cannot be undone.").classes("text-gray-500")

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                def delete():
                    for prompt_id in list(self.selected_ids):
                        self.store.delete_prompt(prompt_id)
                    self.selected_ids.clear()
                    self._render_prompts()
                    self._update_selection_label()
                    self.on_selection_change([])
                    dialog.close()
                    ui.notify(f"Deleted {count} prompt(s)", type="positive")

                ui.button("Delete", on_click=delete).props("color=negative")

        dialog.open()

    def refresh(self) -> None:
        """Refresh the prompt list."""
        self._render_prompts()
        self._update_selection_label()
