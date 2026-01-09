"""Results view UI component."""

import csv
import io
from datetime import datetime

from nicegui import ui

from ..lib.aws_config import build_cloudwatch_session_url, get_agentcore_region
from ..lib.models import InvocationResult, InvocationStatus


class ResultsView:
    """UI component for displaying invocation results."""

    def __init__(self):
        self.results: list[InvocationResult] = []
        self._results_container = None
        self._count_label = None

    def render(self) -> None:
        """Render the results view panel."""
        with ui.card().classes("w-full"):
            with ui.row().classes("w-full items-center justify-between mb-2"):
                ui.label("Results").classes("text-lg font-bold")
                with ui.row().classes("gap-2"):
                    self._count_label = ui.label("0 results").classes("text-sm text-gray-500")
                    ui.button("Export CSV", on_click=self._export_csv, icon="download").props(
                        "dense flat"
                    )
                    ui.button("Clear", on_click=self._clear_results, icon="clear").props(
                        "dense flat"
                    )

            # Results container
            self._results_container = ui.column().classes("w-full max-h-96 overflow-y-auto")
            self._render_results()

    def _render_results(self) -> None:
        """Render the results list."""
        self._results_container.clear()

        with self._results_container:
            if not self.results:
                ui.label("No results yet. Run some prompts to see results here.").classes(
                    "text-gray-400 italic p-4"
                )
                return

            # Header row
            with ui.row().classes(
                "w-full items-center gap-2 p-2 bg-gray-100 rounded font-medium text-sm"
            ):
                ui.label("Status").classes("w-20")
                ui.label("Prompt").classes("flex-grow")
                ui.label("Duration").classes("w-20 text-right")
                ui.label("").classes("w-8")  # Expand button space

            # Result rows
            for result in self.results:
                self._render_result_row(result)

    def _render_result_row(self, result: InvocationResult) -> None:
        """Render a single result row."""
        status_config = self._get_status_config(result.status)
        icon_name = status_config["icon"]
        icon_color = status_config["color"]

        with ui.expansion(text="", value=False).classes("w-full") as expansion:
            # Custom header slot showing status, name, and duration
            with expansion.add_slot("header"):
                with ui.row().classes("w-full items-center gap-3"):
                    ui.icon(icon_name, color=icon_color).classes("text-lg")
                    ui.label(result.prompt_name).classes("flex-grow font-medium truncate")
                    ui.label(result.duration_display).classes(
                        "text-sm text-gray-500 min-w-16 text-right"
                    )

            # Expansion content
            with ui.column().classes("w-full p-2 bg-gray-50 rounded mt-2"):
                ui.label("Prompt:").classes("text-xs text-gray-500")
                ui.label(result.prompt_text).classes("text-sm mb-2 whitespace-pre-wrap")

                if result.status == InvocationStatus.SUCCESS:
                    ui.label("Response:").classes("text-xs text-gray-500")
                    ui.label(result.result or "No result").classes(
                        "text-sm whitespace-pre-wrap break-words"
                    )
                elif result.status == InvocationStatus.RUNNING:
                    with ui.row().classes("items-center gap-2"):
                        ui.spinner(size="sm")
                        ui.label("Running...").classes("text-sm text-gray-500")
                elif result.status == InvocationStatus.PENDING:
                    ui.label("Waiting to start...").classes("text-sm text-gray-500 italic")
                else:
                    ui.label("Error:").classes("text-xs text-red-500")
                    ui.label(result.error_message or "Unknown error").classes(
                        "text-sm text-red-700 whitespace-pre-wrap"
                    )

                # Timing and session info
                with ui.row().classes("w-full gap-4 mt-2 text-xs text-gray-400"):
                    if result.started_at:
                        ui.label(f"Started: {result.started_at.strftime('%H:%M:%S')}")
                    if result.completed_at:
                        ui.label(f"Completed: {result.completed_at.strftime('%H:%M:%S')}")

                if result.session_id:
                    with ui.column().classes("gap-1 mt-1"):
                        with ui.row().classes("items-center gap-1"):
                            ui.label("Session:").classes("text-xs text-gray-400")
                            # Try to build deep link URL, fall back to basic dashboard
                            dashboard_url = build_cloudwatch_session_url(
                                result.session_id, agent=result.agent
                            )
                            if not dashboard_url:
                                region = (
                                    result.agent.region if result.agent else get_agentcore_region()
                                )
                                dashboard_url = (
                                    f"https://console.aws.amazon.com/cloudwatch/home"
                                    f"?region={region}#gen-ai-observability/agent-core"
                                )
                            ui.link(
                                result.session_id,
                                dashboard_url,
                                new_tab=True,
                            ).classes("text-xs font-mono text-blue-600 hover:underline")
                        ui.label(
                            "(Note: Traces may take up to 30 seconds to appear "
                            "in observability portal)"
                        ).classes("text-xs text-gray-400 italic")

    def _get_status_config(self, status: InvocationStatus) -> dict:
        """Get icon and color configuration for a status."""
        configs = {
            InvocationStatus.PENDING: {"icon": "schedule", "color": "gray"},
            InvocationStatus.RUNNING: {"icon": "hourglass_empty", "color": "orange"},
            InvocationStatus.SUCCESS: {"icon": "check_circle", "color": "green"},
            InvocationStatus.ERROR: {"icon": "error", "color": "red"},
            InvocationStatus.TIMEOUT: {"icon": "timer_off", "color": "red"},
        }
        return configs.get(status, {"icon": "help", "color": "gray"})

    def add_or_update_result(self, result: InvocationResult) -> None:
        """Add a new result or update existing one."""
        # Find existing result by prompt_id
        for i, existing in enumerate(self.results):
            if existing.prompt_id == result.prompt_id:
                self.results[i] = result
                self._render_results()
                self._update_count()
                return

        # Add new result
        self.results.append(result)
        self._render_results()
        self._update_count()

    def _update_count(self) -> None:
        """Update the results count label."""
        count = len(self.results)
        self._count_label.text = f"{count} result{'s' if count != 1 else ''}"

    def _clear_results(self) -> None:
        """Clear all results."""
        self.results.clear()
        self._render_results()
        self._update_count()

    def _export_csv(self) -> None:
        """Export results to CSV."""
        if not self.results:
            ui.notify("No results to export", type="warning")
            return

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        headers = [
            "Prompt Name",
            "Prompt Text",
            "Status",
            "Duration (s)",
            "Result/Error",
            "Started",
            "Completed",
            "Session ID",
        ]
        writer.writerow(headers)

        # Data rows
        for result in self.results:
            if result.status == InvocationStatus.SUCCESS:
                result_or_error = result.result
            else:
                result_or_error = result.error_message
            started = result.started_at.isoformat() if result.started_at else ""
            completed = result.completed_at.isoformat() if result.completed_at else ""
            writer.writerow(
                [
                    result.prompt_name,
                    result.prompt_text,
                    result.status.value,
                    result.duration_seconds or "",
                    result_or_error,
                    started,
                    completed,
                    result.session_id or "",
                ]
            )

        csv_content = output.getvalue()

        # Trigger download
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"agent_results_{timestamp}.csv"

        ui.download(csv_content.encode(), filename)
        ui.notify(f"Exported {len(self.results)} results to {filename}", type="positive")

    def clear(self) -> None:
        """Public method to clear results."""
        self._clear_results()
