"""
Command-line interface and pipeline orchestration.
"""

import argparse
import sys

from .analysis import calculate_averages, calculate_running_metrics
from .db import fetch_heart_rate_data, fetch_running_raw_data, open_database
from .visualization import output_console, output_graph


def build_parser() -> argparse.ArgumentParser:
    """Builds and returns the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Analyze Android Health Connect heart rate data."
    )
    parser.add_argument(
        "db_file",
        type=str,
        help="Path to the Health Connect SQLite database file (or a ZIP archive containing it)."
    )
    parser.add_argument(
        "--max-bpm",
        type=int,
        default=None,
        help="Ignore heart rates above this value (default: no upper limit)."
    )
    parser.add_argument(
        "--output",
        type=str,
        choices=['console', 'graph'],
        default='console',
        help="Output format (default: console)."
    )
    parser.add_argument(
        "--no-runs",
        action="store_true",
        help="Exclude running sessions from output."
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Main execution entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    with open_database(args.db_file) as conn:
        df = fetch_heart_rate_data(conn)
        if df is None:
            sys.exit(1)

        latest_time = df.index[-1]
        latest_bpm = df.iloc[-1]['beats_per_minute']
        print(f"Latest heartbeat record: {latest_time.strftime('%Y-%m-%d %H:%M:%S')} ({latest_bpm} BPM)")

        runs = None
        if not args.no_runs:
            raw_runs = fetch_running_raw_data(conn)
            if raw_runs is not None:
                runs_df, speed_df, cadence_df, steps_df = raw_runs
                runs = calculate_running_metrics(
                    runs_df,
                    hr_df=df,
                    speed_df=speed_df,
                    cadence_df=cadence_df,
                    steps_df=steps_df
                )

        resting_df = df
        if args.max_bpm is not None:
            print(f"Filtering resting averages: Ignoring heart rates above {args.max_bpm} BPM.")
            resting_df = df[df['beats_per_minute'] <= args.max_bpm]

        daily, weekly, monthly = calculate_averages(resting_df)

        if args.output == 'console':
            output_console(daily, weekly, monthly, runs)
        elif args.output == 'graph':
            output_graph(daily, weekly, monthly, runs)


if __name__ == "__main__":
    main()
