"""
Android Health Connect Data Explorer

Modular package for extracting, analyzing, and visualizing health data
exported from Android Health Connect (SQLite databases or ZIP archives).
"""

from .analysis import calculate_averages, calculate_running_metrics, format_pace
from .db import (
    connect_db,
    fetch_heart_rate_data,
    fetch_running_raw_data,
    get_tables,
    inspect_table_columns,
    open_database,
)
from .visualization import (
    build_heart_rate_tab,
    build_running_tab,
    output_console,
    output_graph,
)


def fetch_running_sessions_data(conn, hr_df=None):
    """Convenience helper fetching raw running data and calculating metrics."""
    raw = fetch_running_raw_data(conn)
    if raw is None:
        return None
    runs_df, speed_df, cadence_df, steps_df = raw
    return calculate_running_metrics(
        runs_df,
        hr_df=hr_df,
        speed_df=speed_df,
        cadence_df=cadence_df,
        steps_df=steps_df,
    )


__all__ = [
    "connect_db",
    "open_database",
    "get_tables",
    "inspect_table_columns",
    "fetch_heart_rate_data",
    "fetch_running_raw_data",
    "fetch_running_sessions_data",
    "calculate_averages",
    "calculate_running_metrics",
    "format_pace",
    "build_heart_rate_tab",
    "build_running_tab",
    "output_console",
    "output_graph",
]
