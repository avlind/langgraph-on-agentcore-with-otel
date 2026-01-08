#!/usr/bin/env python3
"""
Pretty formatter for CloudWatch logs with JSON OpenTelemetry format.
Reads JSON logs from stdin and outputs human-readable format.
"""
import sys
import json
from datetime import datetime


# ANSI color codes
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

    # Severity colors
    ERROR = '\033[91m'    # Bright red
    WARN = '\033[93m'     # Bright yellow
    INFO = '\033[94m'     # Bright blue
    DEBUG = '\033[90m'    # Gray

    # Component colors
    TIMESTAMP = '\033[36m'  # Cyan
    TRACE_ID = '\033[35m'   # Magenta
    FILE = '\033[90m'       # Gray


def get_severity_color(severity: str) -> str:
    """Get color code for severity level."""
    severity_upper = severity.upper()
    if severity_upper == 'ERROR':
        return Colors.ERROR
    elif severity_upper in ('WARN', 'WARNING'):
        return Colors.WARN
    elif severity_upper == 'INFO':
        return Colors.INFO
    else:
        return Colors.DEBUG


def format_timestamp(ts_str: str) -> str:
    """Format timestamp string."""
    try:
        # Parse ISO format timestamp
        dt = datetime.fromisoformat(ts_str.replace('+00:00', ''))
        return dt.strftime('%H:%M:%S.%f')[:-3]  # HH:MM:SS.mmm
    except:
        return ts_str


def format_log_entry(timestamp: str, log_data: dict) -> str:
    """Format a single log entry for pretty output."""
    try:
        # Extract key fields
        severity = log_data.get('severityText', 'INFO')
        body = log_data.get('body', '')

        # Skip empty bodies
        if not body:
            return None

        # Get trace/span info if available
        attributes = log_data.get('attributes', {})
        trace_id = attributes.get('otelTraceID', '')

        # Get file location if available
        file_path = attributes.get('code.file.path', '')
        line_num = attributes.get('code.line.number', '')

        # Format timestamp
        time_str = format_timestamp(timestamp)

        # Build output
        parts = []

        # Timestamp (cyan)
        parts.append(f"{Colors.TIMESTAMP}{time_str}{Colors.RESET}")

        # Severity with color
        severity_color = get_severity_color(severity)
        severity_padded = f"{severity:5s}"
        parts.append(f"{severity_color}{severity_padded}{Colors.RESET}")

        # Message body (convert to string if needed)
        body_str = str(body) if not isinstance(body, str) else body
        parts.append(body_str)

        # Add trace ID if present and not "0"
        if trace_id and trace_id != "0":
            trace_short = trace_id[:8]
            parts.append(f"{Colors.DIM}[trace:{trace_short}]{Colors.RESET}")

        # Add file location if in debug mode or for errors
        if file_path and (severity.upper() in ('ERROR', 'WARN') or '--debug' in sys.argv):
            file_short = file_path.split('/')[-1] if '/' in file_path else file_path
            location = f"{file_short}:{line_num}" if line_num else file_short
            parts.append(f"{Colors.FILE}({location}){Colors.RESET}")

        return " ".join(parts)

    except Exception as e:
        # If parsing fails, skip this entry (return None to filter out)
        return None


def main():
    """Process logs from stdin and output pretty format."""
    print(f"{Colors.BOLD}📋 Agent Runtime Logs (press Ctrl+C to stop){Colors.RESET}")
    print(f"{Colors.DIM}{'─' * 100}{Colors.RESET}\n")

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            # Parse log line format: timestamp stream_name json_data
            parts = line.split(' ', 2)
            if len(parts) < 3:
                continue

            timestamp = parts[0]
            # stream_name = parts[1]  # Usually "otel-rt-logs"
            json_data = parts[2]

            try:
                log_data = json.loads(json_data)
                formatted = format_log_entry(timestamp, log_data)
                if formatted:  # Only print if format was successful
                    print(formatted)
                    sys.stdout.flush()
            except json.JSONDecodeError:
                # Not JSON, skip it silently (likely non-log line)
                pass

    except KeyboardInterrupt:
        print(f"\n\n{Colors.BOLD}Log streaming stopped{Colors.RESET}")
    except BrokenPipeError:
        # Handle pipe being closed
        pass


if __name__ == "__main__":
    main()
