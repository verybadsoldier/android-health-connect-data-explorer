"""
Database operations, archive handling, and SQL queries for Android Health Connect data.
"""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import sys
import tempfile
import zipfile
import pandas as pd


def connect_db(db_path: str | Path) -> sqlite3.Connection:
    """Establishes a connection to the SQLite database."""
    path = Path(db_path)
    if not path.exists():
        print(f"Error: Database file not found at {path}", file=sys.stderr)
        sys.exit(1)

    try:
        return sqlite3.connect(path)
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}", file=sys.stderr)
        sys.exit(1)


@contextmanager
def open_database(db_path: str | Path):
    """
    Context manager to safely open and close an SQLite database,
    transparently extracting it if a ZIP archive is provided.
    """
    path = Path(db_path)
    if not path.exists():
        print(f"Error: Database file not found at {path}", file=sys.stderr)
        sys.exit(1)

    temp_dir = None
    resolved_path = path

    if path.is_file() and zipfile.is_zipfile(path):
        print("Extracting database from ZIP archive...")
        temp_dir = tempfile.TemporaryDirectory()
        with zipfile.ZipFile(path, "r") as z:
            db_filename = next((name for name in z.namelist() if name.endswith((".db", ".sqlite"))), None)
            if not db_filename and z.namelist():
                db_filename = z.namelist()[0]

            if db_filename:
                resolved_path = Path(z.extract(db_filename, temp_dir.name))
            else:
                print("Error: No files found in the ZIP archive.", file=sys.stderr)
                if temp_dir:
                    temp_dir.cleanup()
                sys.exit(1)

    conn = connect_db(resolved_path)
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass
        if temp_dir:
            temp_dir.cleanup()


def get_tables(conn: sqlite3.Connection) -> set[str]:
    """Returns the set of all table names in the database."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    return {r[0] for r in cursor.fetchall()}


def inspect_table_columns(conn: sqlite3.Connection, table_name: str) -> None:
    """
    Inspects and prints the columns of a specific table.
    Helper function to diagnose schema differences.
    """
    print(f"--- Inspecting columns for table: {table_name} ---")
    try:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()

        if not columns:
            print(f"Table '{table_name}' not found or is empty.", file=sys.stderr)
            return

        print(f"Found {len(columns)} columns:")
        print("Index | Column Name      | Data Type")
        print("--------------------------------------")
        for col in columns:
            print(f"{col[0]:<5} | {col[1]:<16} | {col[2]}")

        print("\n--- ACTION REQUIRED ---")
        print("1. Identify the column name for the timestamp (e.g., 'epoch_millis').")
        print("2. Identify the column name for the heart rate (e.g., 'beats_per_minute').")
        print("3. Update the query in 'fetch_heart_rate_data' if needed.")

    except sqlite3.Error as e:
        print(f"Error inspecting table {table_name}: {e}", file=sys.stderr)


def fetch_heart_rate_data(conn: sqlite3.Connection, max_bpm: int | None = None) -> pd.DataFrame | None:
    """
    Fetches raw heart rate series data from 'heart_rate_record_series_table'.
    """
    sql_query = """
    SELECT
        epoch_millis,
        beats_per_minute
    FROM
        heart_rate_record_series_table
    WHERE
        beats_per_minute > 0
    """
    params = []

    if max_bpm is not None:
        sql_query += " AND beats_per_minute <= ?"
        params.append(max_bpm)
        print(f"Filtering query: Ignoring heart rates above {max_bpm} BPM.")

    sql_query += ";"

    try:
        df = pd.read_sql_query(
            sql_query,
            conn,
            params=params,
            parse_dates={'epoch_millis': {'unit': 'ms'}}
        )

        if df.empty:
            print("No heart rate data found with the current query.", file=sys.stderr)
            return None

        df.set_index('epoch_millis', inplace=True)
        df.sort_index(inplace=True)
        return df

    except pd.errors.DatabaseError as e:
        print(f"SQL Error: {e}", file=sys.stderr)
        print("This likely means the assumed table 'heart_rate_record_series_table' or")
        print("columns 'time'/'beats_per_minute' do not exist.")
        print("Please inspect your database and update the SQL query.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during data fetching: {e}", file=sys.stderr)
        return None


def fetch_running_raw_data(conn: sqlite3.Connection):
    """
    Fetches raw running sessions and related granular series
    (speed, cadence, steps) from the database.
    """
    tables = get_tables(conn)
    if 'exercise_session_record_table' not in tables:
        return None

    dist_expr = "NULL"
    if 'exercise_laps_table' in tables and 'distance_record_table' in tables:
        dist_expr = """coalesce(
            (SELECT sum(lap_length) FROM exercise_laps_table l WHERE l.parent_key = e.row_id),
            (SELECT sum(distance) FROM distance_record_table d WHERE d.start_time >= e.start_time AND d.end_time <= e.end_time AND d.app_info_id = e.app_info_id),
            (SELECT sum(distance) FROM distance_record_table d WHERE d.start_time >= e.start_time AND d.end_time <= e.end_time)
        )"""
    elif 'exercise_laps_table' in tables:
        dist_expr = "(SELECT sum(lap_length) FROM exercise_laps_table l WHERE l.parent_key = e.row_id)"
    elif 'distance_record_table' in tables:
        dist_expr = """coalesce(
            (SELECT sum(distance) FROM distance_record_table d WHERE d.start_time >= e.start_time AND d.end_time <= e.end_time AND d.app_info_id = e.app_info_id),
            (SELECT sum(distance) FROM distance_record_table d WHERE d.start_time >= e.start_time AND d.end_time <= e.end_time)
        )"""

    pause_expr = "0"
    if 'exercise_segments_table' in tables:
        pause_expr = """coalesce(
            (SELECT sum(segment_end_time - segment_start_time) FROM exercise_segments_table s WHERE s.parent_key = e.row_id AND s.segment_type = 67),
            0
        )"""

    # 33 = EXERCISE_SESSION_TYPE_RUNNING, 34 = EXERCISE_SESSION_TYPE_RUNNING_TREADMILL
    query = f"""
        SELECT
            e.row_id,
            e.app_info_id,
            e.start_time,
            e.end_time,
            e.exercise_type,
            coalesce(e.title, 'Running') as title,
            {dist_expr} as distance_meters,
            {pause_expr} as pause_ms
        FROM exercise_session_record_table e
        WHERE e.exercise_type IN (33, 34)
           OR lower(coalesce(e.title, '')) LIKE '%lauf%'
           OR lower(coalesce(e.title, '')) LIKE '%run%'
        ORDER BY e.start_time ASC
    """
    try:
        runs = pd.read_sql_query(query, conn)
    except Exception as e:
        print(f"Warning: Could not fetch running sessions: {e}", file=sys.stderr)
        return None

    if runs.empty:
        return None

    speed_df = None
    if 'speed_record_table' in tables:
        try:
            speed_df = pd.read_sql_query(
                "SELECT epoch_millis, speed FROM speed_record_table WHERE speed > 0",
                conn,
                parse_dates={'epoch_millis': {'unit': 'ms'}}
            )
            if not speed_df.empty:
                speed_df.set_index('epoch_millis', inplace=True)
                speed_df.sort_index(inplace=True)
        except Exception:
            speed_df = None

    cadence_df = None
    if 'steps_cadence_record_table' in tables:
        try:
            cadence_df = pd.read_sql_query(
                "SELECT epoch_millis, rate FROM steps_cadence_record_table WHERE rate > 0",
                conn,
                parse_dates={'epoch_millis': {'unit': 'ms'}}
            )
            if not cadence_df.empty:
                cadence_df.set_index('epoch_millis', inplace=True)
                cadence_df.sort_index(inplace=True)
        except Exception:
            cadence_df = None

    steps_df = None
    if 'steps_record_table' in tables:
        try:
            steps_df = pd.read_sql_query(
                """
                SELECT app_info_id, start_time, end_time, count
                FROM steps_record_table
                WHERE (end_time - start_time) <= 600000 AND count > 0
                ORDER BY start_time
                """,
                conn
            )
        except Exception:
            steps_df = None

    return runs, speed_df, cadence_df, steps_df
