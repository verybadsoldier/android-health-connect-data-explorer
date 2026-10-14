"""
Heart rate topic facade re-exporting data fetching, averaging, and tab creation.
"""

from .analysis import calculate_averages
from .db import fetch_heart_rate_data
from .visualization import build_heart_rate_tab

__all__ = [
    "fetch_heart_rate_data",
    "calculate_averages",
    "build_heart_rate_tab",
]
