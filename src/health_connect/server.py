"""
Local HTTP server providing real-time API endpoints and serving the modern web dashboard.
"""

from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import socket
import sys
import urllib.parse
import webbrowser

import numpy as np
import pandas as pd

from .analysis import calculate_averages, calculate_running_metrics, format_pace
from .db import fetch_heart_rate_data, fetch_running_raw_data, open_database

WEB_DIR = Path(__file__).resolve().parent / "web"


def _clean_val(v):
    """Converts numpy/pandas NaN or infinity values into JSON-friendly None."""
    if v is None or pd.isna(v) or (isinstance(v, float) and (np.isneginf(v) or np.isposinf(v))):
        return None
    if isinstance(v, (np.integer, np.floating)):
        return v.item()
    return v


def get_dataset_payload(db_path: str | Path, max_bpm: int | None = None, no_runs: bool = False) -> dict:
    """Extracts and prepares data for the web UI JSON payload."""
    db_path = Path(db_path)
    with open_database(db_path) as conn:
        df = fetch_heart_rate_data(conn)
        if df is None:
            return {"error": "No heart rate data found"}

        latest_time = df.index[-1]
        latest_bpm = int(df.iloc[-1]['beats_per_minute'])

        runs_list = []
        runs_df = None
        if not no_runs:
            raw_runs = fetch_running_raw_data(conn)
            if raw_runs is not None:
                r_df, speed_df, cadence_df, steps_df = raw_runs
                runs_df = calculate_running_metrics(
                    r_df,
                    hr_df=df,
                    speed_df=speed_df,
                    cadence_df=cadence_df,
                    steps_df=steps_df
                )

        resting_df = df
        if max_bpm is not None:
            resting_df = df[df['beats_per_minute'] <= max_bpm]

        daily, weekly, monthly = calculate_averages(resting_df)

        # Build resting HR lists
        daily_records = []
        for dt, row in daily.iterrows():
            daily_records.append({
                "date": dt.strftime('%Y-%m-%d'),
                "bpm": round(float(row['beats_per_minute']), 1)
            })

        weekly_records = []
        for dt, row in weekly.iterrows():
            weekly_records.append({
                "date": dt.strftime('%Y-%m-%d'),
                "label": dt.strftime('%Y - W%W'),
                "bpm": round(float(row['beats_per_minute']), 1)
            })

        monthly_records = []
        for dt, row in monthly.iterrows():
            monthly_records.append({
                "date": dt.strftime('%Y-%m-%d'),
                "label": dt.strftime('%Y-%m'),
                "bpm": round(float(row['beats_per_minute']), 1)
            })

        # Build running records
        if runs_df is not None and not runs_df.empty:
            for idx, r in runs_df.iterrows():
                runs_list.append({
                    "id": int(r['row_id']) if 'row_id' in r and pd.notna(r['row_id']) else int(idx),
                    "date": r['start_dt'].strftime('%Y-%m-%d %H:%M'),
                    "date_short": r['start_dt'].strftime('%Y-%m-%d'),
                    "timestamp": int(r['start_dt'].timestamp() * 1000),
                    "duration_min": _clean_val(round(r['duration_min'], 1)),
                    "distance_km": _clean_val(round(r['distance_km'], 2)),
                    "pace_str": format_pace(r['pace_min_km']),
                    "pace_min_km": _clean_val(round(r['pace_min_km'], 2)),
                    "speed_kmh": _clean_val(round(r['speed_kmh'], 1)),
                    "speed1_kmh": _clean_val(round(r['speed1_kmh'], 1)),
                    "speed2_kmh": _clean_val(round(r['speed2_kmh'], 1)),
                    "avg_bpm": _clean_val(round(r['avg_bpm'], 1)),
                    "max_bpm": _clean_val(int(r['max_bpm'])) if pd.notna(r['max_bpm']) else None,
                    "min_bpm": _clean_val(int(r['min_bpm'])) if pd.notna(r['min_bpm']) else None,
                    "hr1": _clean_val(round(r['hr1'], 1)),
                    "hr2": _clean_val(round(r['hr2'], 1)),
                    "cadence": _clean_val(round(r['cadence'], 1)),
                    "cadence1": _clean_val(round(r['cadence1'], 1)),
                    "cadence2": _clean_val(round(r['cadence2'], 1)),
                    "stride_m": _clean_val(round(r['stride_m'], 2)),
                    "stride1_m": _clean_val(round(r['stride1_m'], 2)),
                    "stride2_m": _clean_val(round(r['stride2_m'], 2)),
                    "ef": _clean_val(round(r['ef'], 3)),
                    "ef1": _clean_val(round(r['ef1'], 3)),
                    "ef2": _clean_val(round(r['ef2'], 3)),
                    "drift_pct": _clean_val(round(r['drift_pct'], 1)),
                })

        # Calculate summary statistics
        summary = {
            "total_runs": len(runs_list),
            "total_distance_km": round(sum(r['distance_km'] for r in runs_list if r['distance_km']), 1) if runs_list else 0,
            "total_duration_hours": round(sum(r['duration_min'] for r in runs_list if r['duration_min']) / 60.0, 1) if runs_list else 0,
            "avg_ef": round(float(np.nanmean([r['ef'] for r in runs_list if r['ef']])), 3) if runs_list and any(r['ef'] for r in runs_list) else None,
            "avg_drift": round(float(np.nanmean([r['drift_pct'] for r in runs_list if r['drift_pct'] is not None])), 1) if runs_list and any(r['drift_pct'] is not None for r in runs_list) else None,
            "avg_pace": format_pace(float(np.nanmean([r['pace_min_km'] for r in runs_list if r['pace_min_km']]))) if runs_list and any(r['pace_min_km'] for r in runs_list) else "-",
            "avg_cadence": round(float(np.nanmean([r['cadence'] for r in runs_list if r['cadence']])), 1) if runs_list and any(r['cadence'] for r in runs_list) else None,
            "avg_stride_m": round(float(np.nanmean([r['stride_m'] for r in runs_list if r['stride_m']])), 2) if runs_list and any(r['stride_m'] for r in runs_list) else None,
            "avg_resting_hr": round(float(daily['beats_per_minute'].mean()), 1) if not daily.empty else None,
            "min_resting_hr": round(float(daily['beats_per_minute'].min()), 1) if not daily.empty else None,
            "days_recorded": len(daily),
        }

        return {
            "db_name": db_path.name,
            "latest_heartbeat": {
                "timestamp": latest_time.strftime('%Y-%m-%d %H:%M:%S'),
                "bpm": latest_bpm
            },
            "summary": summary,
            "heart_rate": {
                "daily": daily_records,
                "weekly": weekly_records,
                "monthly": monthly_records,
            },
            "running": runs_list,
        }


def get_bokeh_html_payload(db_path: str | Path, max_bpm: int | None = None, no_runs: bool = False) -> str:
    """Generates the interactive Bokeh HTML dashboard string."""
    db_path = Path(db_path)
    with open_database(db_path) as conn:
        df = fetch_heart_rate_data(conn)
        if df is None:
            return "<h3>Error: No heart rate data found in database.</h3>"

        runs = None
        if not no_runs:
            raw_runs = fetch_running_raw_data(conn)
            if raw_runs is not None:
                r_df, speed_df, cadence_df, steps_df = raw_runs
                runs = calculate_running_metrics(
                    r_df,
                    hr_df=df,
                    speed_df=speed_df,
                    cadence_df=cadence_df,
                    steps_df=steps_df
                )

        resting_df = df
        if max_bpm is not None:
            resting_df = df[df['beats_per_minute'] <= max_bpm]

        daily, weekly, monthly = calculate_averages(resting_df)
        from .visualization import generate_bokeh_html
        return generate_bokeh_html(daily, weekly, monthly, runs)


class HealthConnectRequestHandler(SimpleHTTPRequestHandler):
    """Custom HTTP request handler serving static frontend files and real-time JSON API."""

    def __init__(self, *args, db_path: Path, max_bpm: int | None = None, no_runs: bool = False, **kwargs):
        self.db_path = db_path
        self.current_max_bpm = max_bpm
        self.no_runs = no_runs
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/bokeh":
            try:
                html = get_bokeh_html_payload(self.db_path, max_bpm=self.current_max_bpm, no_runs=self.no_runs)
                payload = html.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                err_payload = f"<h3>Error generating Bokeh view: {e}</h3>".encode("utf-8")
                self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(err_payload)))
                self.end_headers()
                self.wfile.write(err_payload)
            return

        if path == "/api/data":
            query = urllib.parse.parse_qs(parsed.query)
            bpm_param = query.get("max_bpm", [None])[0]
            max_bpm = int(bpm_param) if bpm_param and bpm_param != "null" and bpm_param != "0" else self.current_max_bpm
            no_runs_param = query.get("no_runs", [None])[0]
            no_runs = no_runs_param == "true" if no_runs_param else self.no_runs

            try:
                data = get_dataset_payload(self.db_path, max_bpm=max_bpm, no_runs=no_runs)
                payload = json.dumps(data).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(payload)
            except Exception as e:
                err_payload = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(err_payload)))
                self.end_headers()
                self.wfile.write(err_payload)
            return

        if path in ("", "/"):
            self.path = "/index.html"

        super().do_GET()

    def log_message(self, format, *args):
        # Keep terminal output clean, suppress standard GET asset logs
        if self.path.startswith("/api/"):
            super().log_message(format, *args)


def find_available_port(start_port: int = 8000, max_attempts: int = 20) -> int:
    """Finds an open TCP port starting at start_port."""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return start_port


def start_server(
    db_path: str | Path,
    port: int = 8000,
    max_bpm: int | None = None,
    no_runs: bool = False,
    open_browser: bool = True
) -> None:
    """Starts the web dashboard HTTP server and opens it in the default browser."""
    db_path = Path(db_path)
    port = find_available_port(port)

    handler = partial(
        HealthConnectRequestHandler,
        db_path=db_path,
        max_bpm=max_bpm,
        no_runs=no_runs
    )

    server = ThreadingHTTPServer(('127.0.0.1', port), handler)
    url = f"http://127.0.0.1:{port}"

    print(f"\n=======================================================")
    print(f"  Health Connect Explorer Web App running at:")
    print(f"  --> {url}")
    print(f"  Press Ctrl+C to stop the server")
    print(f"=======================================================\n")

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down web server...")
    finally:
        server.server_close()
