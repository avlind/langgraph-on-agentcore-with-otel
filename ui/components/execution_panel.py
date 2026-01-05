"""Execution panel UI component."""

from nicegui import ui

from ..lib.aws_config import get_aws_profiles, get_current_profile
from ..lib.models import AppConfig, InvocationResult, InvocationStatus, Prompt


class ExecutionPanel:
    """UI component for execution controls and progress."""

    def __init__(
        self,
        config: AppConfig,
        on_run_selected: callable,
        on_run_all: callable,
        on_cancel: callable,
        on_config_change: callable,
    ):
        self.config = config
        self.on_run_selected = on_run_selected
        self.on_run_all = on_run_all
        self.on_cancel = on_cancel
        self.on_config_change = on_config_change

        self.selected_count = 0
        self.total_count = 0
        self.is_running = False

        # Progress tracking
        self.running_count = 0
        self.success_count = 0
        self.error_count = 0
        self.completed_count = 0
        self._result_statuses: dict[str, InvocationStatus] = {}  # Track previous status

        # UI elements
        self._selected_label = None
        self._progress_bar = None
        self._progress_label = None
        self._status_label = None
        self._run_selected_btn = None
        self._run_all_btn = None
        self._cancel_btn = None

    def render(self) -> None:
        """Render the execution panel."""
        with ui.card().classes("w-full"):
            ui.label("Execution").classes("text-lg font-bold mb-2")

            # AWS Profile selector
            profiles = get_aws_profiles()
            current = get_current_profile()
            if current in profiles:
                default_profile = current
            else:
                default_profile = profiles[0] if profiles else "default"

            ui.select(
                label="AWS Profile",
                options=profiles,
                value=default_profile,
                on_change=lambda e: self._update_profile(e.value),
            ).classes("w-full mb-2")

            # Sync the config with the actual selected profile value
            self._update_profile(default_profile)

            # Concurrency slider
            with ui.row().classes("w-full items-center gap-2 mb-2"):
                ui.label("Concurrent:").classes("text-sm")
                ui.slider(
                    min=1,
                    max=20,
                    step=1,
                    value=self.config.max_concurrent,
                    on_change=lambda e: self._update_concurrent(int(e.value)),
                ).classes("flex-grow")
                self._concurrent_label = ui.label(str(self.config.max_concurrent)).classes(
                    "text-sm w-8"
                )

            # Timeout input
            with ui.row().classes("w-full items-center gap-2 mb-4"):
                ui.label("Timeout (sec):").classes("text-sm")
                ui.number(
                    value=self.config.timeout_seconds,
                    min=10,
                    max=600,
                    step=10,
                    on_change=lambda e: self._update_timeout(int(e.value)),
                ).classes("flex-grow")

            # Selection info
            self._selected_label = ui.label("0 prompts selected").classes("text-sm mb-2")

            # Run buttons
            with ui.row().classes("w-full gap-2 mb-4"):
                self._run_selected_btn = ui.button(
                    "Run Selected",
                    on_click=self._handle_run_selected,
                    icon="play_arrow",
                ).props("color=primary")

                self._run_all_btn = ui.button(
                    "Run All",
                    on_click=self._handle_run_all,
                    icon="playlist_play",
                ).props("color=secondary")

                self._cancel_btn = ui.button(
                    "Cancel",
                    on_click=self._handle_cancel,
                    icon="stop",
                ).props("color=negative")
                self._cancel_btn.set_visibility(False)

            # Progress section
            with ui.column().classes("w-full"):
                self._progress_bar = ui.linear_progress(value=0, show_value=False).classes(
                    "w-full mb-1"
                )
                self._progress_label = ui.label("Ready").classes("text-sm text-gray-500")

                # Status counters
                with ui.row().classes("w-full gap-4 mt-2"):
                    with ui.row().classes("items-center gap-1"):
                        ui.icon("hourglass_empty", color="orange").classes("text-sm")
                        self._running_label = ui.label("0").classes("text-sm")
                        ui.label("running").classes("text-xs text-gray-500")

                    with ui.row().classes("items-center gap-1"):
                        ui.icon("check_circle", color="green").classes("text-sm")
                        self._success_label = ui.label("0").classes("text-sm")
                        ui.label("success").classes("text-xs text-gray-500")

                    with ui.row().classes("items-center gap-1"):
                        ui.icon("error", color="red").classes("text-sm")
                        self._error_label = ui.label("0").classes("text-sm")
                        ui.label("failed").classes("text-xs text-gray-500")

    def _update_profile(self, profile: str) -> None:
        """Update AWS profile configuration."""
        self.config.aws_profile = profile
        self.on_config_change(self.config)

    def _update_concurrent(self, value: int) -> None:
        """Update concurrency configuration."""
        self.config.max_concurrent = value
        self._concurrent_label.text = str(value)
        self.on_config_change(self.config)

    def _update_timeout(self, value: int) -> None:
        """Update timeout configuration."""
        self.config.timeout_seconds = value
        self.on_config_change(self.config)

    def _handle_run_selected(self) -> None:
        """Handle run selected button click."""
        if self.selected_count == 0:
            ui.notify("No prompts selected", type="warning")
            return
        self.on_run_selected()

    def _handle_run_all(self) -> None:
        """Handle run all button click."""
        if self.total_count == 0:
            ui.notify("No prompts available", type="warning")
            return
        self.on_run_all()

    def _handle_cancel(self) -> None:
        """Handle cancel button click."""
        self.on_cancel()

    def update_selection(self, selected: list[Prompt], total: int) -> None:
        """Update selection count display."""
        self.selected_count = len(selected)
        self.total_count = total
        self._selected_label.text = f"{self.selected_count} of {total} prompts selected"

    def start_execution(self, total_tasks: int) -> None:
        """Start execution - update UI state."""
        self.is_running = True
        self.total_count = total_tasks
        self.completed_count = 0
        self.running_count = 0
        self.success_count = 0
        self.error_count = 0
        self._result_statuses.clear()  # Clear previous status tracking

        self._run_selected_btn.set_visibility(False)
        self._run_all_btn.set_visibility(False)
        self._cancel_btn.set_visibility(True)

        self._progress_bar.value = 0
        self._progress_label.text = f"Starting... 0/{total_tasks}"
        self._update_counters()

    def update_result(self, result: InvocationResult) -> None:
        """Update progress based on a result."""
        completed_statuses = (
            InvocationStatus.SUCCESS,
            InvocationStatus.ERROR,
            InvocationStatus.TIMEOUT,
        )

        # Get previous status for this prompt (if any)
        prev_status = self._result_statuses.get(result.prompt_id)
        new_status = result.status

        # Only update counters if status actually changed
        if prev_status != new_status:
            self._result_statuses[result.prompt_id] = new_status

            # Handle transition TO running
            if new_status == InvocationStatus.RUNNING:
                self.running_count += 1

            # Handle transition FROM running to completed
            elif new_status in completed_statuses:
                if prev_status == InvocationStatus.RUNNING:
                    self.running_count = max(0, self.running_count - 1)
                self.completed_count += 1

                if new_status == InvocationStatus.SUCCESS:
                    self.success_count += 1
                else:
                    self.error_count += 1

        self._update_counters()
        self._update_progress()

    def _update_counters(self) -> None:
        """Update counter labels."""
        self._running_label.text = str(self.running_count)
        self._success_label.text = str(self.success_count)
        self._error_label.text = str(self.error_count)

    def _update_progress(self) -> None:
        """Update progress bar and label."""
        if self.total_count > 0:
            progress = self.completed_count / self.total_count
            self._progress_bar.value = progress
            self._progress_label.text = f"Progress: {self.completed_count}/{self.total_count}"

    def finish_execution(self) -> None:
        """Finish execution - reset UI state."""
        self.is_running = False
        self.running_count = 0

        self._run_selected_btn.set_visibility(True)
        self._run_all_btn.set_visibility(True)
        self._cancel_btn.set_visibility(False)

        self._progress_label.text = (
            f"Complete: {self.success_count} success, {self.error_count} failed"
        )
        self._update_counters()

    def reset_progress(self) -> None:
        """Reset progress indicators."""
        self.completed_count = 0
        self.running_count = 0
        self.success_count = 0
        self.error_count = 0

        self._progress_bar.value = 0
        self._progress_label.text = "Ready"
        self._update_counters()
