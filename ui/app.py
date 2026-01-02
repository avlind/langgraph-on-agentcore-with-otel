"""Main NiceGUI application for testing AgentCore agents."""

import asyncio

from nicegui import ui

from .components.execution_panel import ExecutionPanel
from .components.prompt_library import PromptLibrary
from .components.results_view import ResultsView
from .lib.agent_invoker import AgentInvoker, InvocationTask
from .lib.aws_config import get_current_profile
from .lib.models import AppConfig, Prompt
from .lib.prompt_store import PromptStore


class AgentTestingApp:
    """Main application controller."""

    def __init__(self):
        # Initialize configuration
        self.config = AppConfig(aws_profile=get_current_profile())

        # Initialize stores and services
        self.prompt_store = PromptStore()
        self.invoker = AgentInvoker(self.config)

        # Track selected prompts
        self.selected_prompts: list[Prompt] = []

        # UI components (initialized during render)
        self.prompt_library: PromptLibrary | None = None
        self.execution_panel: ExecutionPanel | None = None
        self.results_view: ResultsView | None = None

    def render(self) -> None:
        """Render the main application UI."""
        # Dark mode toggle in header
        with ui.header().classes("items-center justify-between"):
            ui.label("AgentCore Testing Dashboard").classes("text-xl font-bold")
            with ui.row().classes("items-center gap-2"):
                ui.label("Dark Mode")
                ui.switch(on_change=lambda e: ui.dark_mode(e.value))

        # Main content
        with ui.column().classes("w-full max-w-7xl mx-auto p-4 gap-4"):
            # Top row: Prompt Library + Execution Panel
            with ui.row().classes("w-full gap-4").style("display: flex; flex-wrap: nowrap"):
                # Prompt Library (left column)
                with ui.column().style("flex: 1 1 50%; min-width: 0"):
                    self.prompt_library = PromptLibrary(
                        store=self.prompt_store,
                        on_selection_change=self._on_selection_change,
                    )
                    self.prompt_library.render()

                # Execution Panel (right column)
                with ui.column().style("flex: 1 1 50%; min-width: 0"):
                    self.execution_panel = ExecutionPanel(
                        config=self.config,
                        on_run_selected=self._run_selected,
                        on_run_all=self._run_all,
                        on_cancel=self._cancel,
                        on_config_change=self._on_config_change,
                    )
                    self.execution_panel.render()
                    self.execution_panel.update_selection([], len(self.prompt_store.list_prompts()))

            # Bottom row: Results
            self.results_view = ResultsView()
            self.results_view.render()

    def _on_selection_change(self, selected: list[Prompt]) -> None:
        """Handle prompt selection change."""
        self.selected_prompts = selected
        if self.execution_panel:
            self.execution_panel.update_selection(selected, len(self.prompt_store.list_prompts()))

    def _on_config_change(self, config: AppConfig) -> None:
        """Handle configuration change."""
        self.config = config
        self.invoker.update_config(config)

    def _run_selected(self) -> None:
        """Run selected prompts."""
        if not self.selected_prompts:
            ui.notify("No prompts selected", type="warning")
            return
        asyncio.create_task(self._run_prompts(self.selected_prompts))

    def _run_all(self) -> None:
        """Run all prompts."""
        all_prompts = self.prompt_store.list_prompts()
        if not all_prompts:
            ui.notify("No prompts available", type="warning")
            return
        asyncio.create_task(self._run_prompts(all_prompts))

    async def _run_prompts(self, prompts: list[Prompt]) -> None:
        """Execute prompts asynchronously."""
        # Clear previous results and reset progress
        self.results_view.clear()
        self.execution_panel.reset_progress()

        # Create tasks
        tasks = [
            InvocationTask(
                prompt_id=p.id,
                prompt_name=p.name,
                prompt_text=p.text,
            )
            for p in prompts
        ]

        # Start execution UI
        self.execution_panel.start_execution(len(tasks))

        def on_status_change(result):
            """Callback for status updates."""
            self.results_view.add_or_update_result(result)
            self.execution_panel.update_result(result)

        try:
            # Run all tasks
            await self.invoker.invoke_batch(tasks, on_status_change)
        except Exception as e:
            ui.notify(f"Execution error: {e}", type="negative")
        finally:
            self.execution_panel.finish_execution()

    def _cancel(self) -> None:
        """Cancel running executions."""
        self.invoker.cancel()
        ui.notify("Cancelling pending invocations...", type="info")


def main():
    """Application entry point."""
    app = AgentTestingApp()

    @ui.page("/")
    def index():
        app.render()

    ui.run(
        title="AgentCore Testing Dashboard",
        favicon="🤖",
        port=8080,
        reload=False,
    )


if __name__ == "__main__":
    main()
