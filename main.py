#!/usr/bin/env python3
"""
Android Health Connect Data Explorer

Main entrypoint for analyzing and visualizing heart rate data and running
sessions from an Android Health Connect SQLite export.
"""
from pathlib import Path
import sys

# Ensure src/ is on sys.path even when not installed in editable mode
src_path = Path(__file__).resolve().parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from health_connect.cli import main
from health_connect.db import connect_db, inspect_table_columns, open_database
from health_connect.formatters import format_pace
from health_connect.heart_rate import calculate_averages, fetch_heart_rate_data
from health_connect.running import calculate_running_metrics, fetch_running_sessions_data
from health_connect.visualization import output_console, output_graph

__all__ = [
    "main",
    "connect_db",
    "open_database",
    "inspect_table_columns",
    "format_pace",
    "fetch_heart_rate_data",
    "calculate_averages",
    "fetch_running_sessions_data",
    "calculate_running_metrics",
    "output_console",
    "output_graph",
]

if __name__ == "__main__":
    main()
