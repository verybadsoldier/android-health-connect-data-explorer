"""
Running sessions topic facade re-exporting data fetching, metrics calculation, and tab creation.
"""

from .analysis import calculate_running_metrics
from .db import fetch_running_raw_data
from .visualization import build_running_tab


def fetch_running_sessions_data(conn, hr_df=None):
    """Fetches raw running sessions and calculates running metrics."""
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
    "fetch_running_raw_data",
    "calculate_running_metrics",
    "fetch_running_sessions_data",
    "build_running_tab",
]
