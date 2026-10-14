#!/usr/bin/env python3

"""
Analyzes heart rate data from an Android Health Connect SQLite export.

Calculates daily, weekly, and monthly heart rate averages and can output
to the console or a graph.

*** NOTE ***
The script is now configured to use the following schema
from 'heart_rate_record_series_table':
- Timestamp column: 'epoch_millis' (as Unix ms)
- Heart rate column: 'beats_per_minute'

If this changes, you may need to update the 'sql_query' in the
'fetch_heart_rate_data' function.
"""

import sqlite3
import pandas as pd
import numpy as np
from bokeh.plotting import figure, show
from bokeh.models import HoverTool, ColumnDataSource, TabPanel, Tabs, Span, DataTable, TableColumn, NumberFormatter
from bokeh.layouts import column
import argparse
import sys
from pathlib import Path
import zipfile
import tempfile

def connect_db(db_path):
    """Establishes a connection to the SQLite database."""
    if not Path(db_path).exists():
        print(f"Error: Database file not found at {db_path}", file=sys.stderr)
        sys.exit(1)
    
    try:
        conn = sqlite3.connect(db_path)
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}", file=sys.stderr)
        sys.exit(1)

def inspect_table_columns(conn, table_name):
    """
    Inspects and prints the columns of a specific table.
    This is a helper function to debug schema issues.
    """
    print(f"--- Inspecting columns for table: {table_name} ---")
    try:
        # Use PRAGMA table_info to get schema information
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
            # col[0] = index, col[1] = name, col[2] = type
            print(f"{col[0]:<5} | {col[1]:<16} | {col[2]}")
        
        print("\n--- ACTION REQUIRED ---")
        print("1. Identify the column name for the timestamp (e.g., 'time', 'sample_time').")
        print("2. Identify the column name for the heart rate (e.g., 'beats_per_minute', 'value').")
        print("3. Update the 'sql_query' in the 'fetch_heart_rate_data' function below.")
        print("4. Comment out the 'inspect_db_and_exit(conn)' line in the 'main' function.")
        print("5. Re-run the script with your desired --output flag.")

    except sqlite3.Error as e:
        print(f"Error inspecting table {table_name}: {e}", file=sys.stderr)

def fetch_heart_rate_data(conn, max_bpm=None):
    """
    Fetches heart rate data from the database.
    
    *** SCHEMA ASSUMPTION ***
    This query now assumes the data is in 'heart_rate_record_series_table'
    with columns:
    - 'epoch_millis': INTEGER (Unix timestamp in milliseconds for the sample)
    - 'beats_per_minute': INTEGER
    
    If your schema is different, you will need to UPDATE THE SQL QUERY below.
    You can use a tool like 'DB Browser for SQLite' to inspect your .db file
    and find the correct table and column names.
    
    Args:
        conn: The SQLite database connection.
        max_bpm: An optional integer. If provided, heart rates above this
                 value will be excluded from the query.
    """
    # --- UPDATE THIS QUERY IF YOUR SCHEMA IS DIFFERENT ---
    # Base query filters out bad (zero) data
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
    # ---------------------------------------------------

    try:
        # 'epoch_millis' will be parsed as our timestamp.
        # We pass the 'params' list for safe, parameterized querying.
        df = pd.read_sql_query(
            sql_query,
            conn,
            params=params,
            parse_dates={'epoch_millis': {'unit': 'ms'}}
        )
        
        if df.empty:
            print("No heart rate data found with the current query.", file=sys.stderr)
            return None

        # Set the timestamp as the index, which is required for resampling
        # If your time column is different, update it here too.
        df.set_index('epoch_millis', inplace=True)
        df.sort_index(inplace=True)
        
        return df

    except pd.errors.DatabaseError as e:
        print(f"SQL Error: {e}", file=sys.stderr)
        print("This likely means the assumed table 'heart_rate_record_series_table' or")
        print("columns 'time'/'beats_per_minute' do not exist.")
        print("Please inspect your database and update the SQL query in the script.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during data fetching: {e}", file=sys.stderr)
        return None

def format_pace(p):
    """Formats numeric pace (minutes per km) as MM:SS min/km."""
    if pd.isna(p) or p <= 0 or p > 30:
        return "-"
    mins = int(p)
    secs = int(round((p - mins) * 60))
    if secs == 60:
        mins += 1
        secs = 0
    return f"{mins}:{secs:02d} min/km"

def fetch_running_sessions_data(conn, hr_df=None):
    """
    Fetches running sessions from 'exercise_session_record_table'
    and calculates duration, distance, pace, speed, heart rate,
    Efficiency Factor (EF), and Aerobic Decoupling (Cardiac Drift).
    """
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {r[0] for r in cursor.fetchall()}
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

    runs['start_dt'] = pd.to_datetime(runs['start_time'], unit='ms')
    runs['end_dt'] = pd.to_datetime(runs['end_time'], unit='ms')
    runs['total_duration_min'] = (runs['end_time'] - runs['start_time']) / 1000.0 / 60.0
    runs['pause_min'] = runs['pause_ms'] / 1000.0 / 60.0
    runs['duration_min'] = np.where(
        (runs['pause_min'] > 0) & (runs['total_duration_min'] > runs['pause_min']),
        runs['total_duration_min'] - runs['pause_min'],
        runs['total_duration_min']
    )
    runs['distance_km'] = runs['distance_meters'] / 1000.0
    runs['pace_min_km'] = runs['duration_min'] / runs['distance_km']
    runs['speed_kmh'] = runs['distance_km'] / (runs['duration_min'] / 60.0)
    runs['mid_dt'] = runs['start_dt'] + (runs['end_dt'] - runs['start_dt']) / 2

    # Fetch speed records for granular half-split calculations if available
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

    # Fetch cadence records if available
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

    # Fetch fine-grained step records for cadence fallback
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

    st_arr = steps_df['start_time'].values if steps_df is not None and not steps_df.empty else None
    et_arr = steps_df['end_time'].values if steps_df is not None and not steps_df.empty else None
    app_arr = steps_df['app_info_id'].values if steps_df is not None and not steps_df.empty else None
    cnt_arr = steps_df['count'].values if steps_df is not None and not steps_df.empty else None

    runs_st = runs['start_time'].values.astype('int64')
    runs_et = runs['end_time'].values.astype('int64')
    runs_md = runs_st + (runs_et - runs_st) // 2

    cad_list, cad1_list, cad2_list = [], [], []
    for i in range(len(runs)):
        dur_min = runs.iloc[i]['duration_min']
        c_val, c1_val, c2_val = np.nan, np.nan, np.nan

        if cadence_df is not None and not cadence_df.empty:
            c_sub = cadence_df.loc[runs.iloc[i]['start_dt']:runs.iloc[i]['end_dt']]
            if not c_sub.empty:
                c_val = round(float(c_sub['rate'].mean()), 1)
                c1_sub = cadence_df.loc[runs.iloc[i]['start_dt']:runs.iloc[i]['mid_dt']]
                c2_sub = cadence_df.loc[runs.iloc[i]['mid_dt']:runs.iloc[i]['end_dt']]
                c1_val = round(float(c1_sub['rate'].mean()), 1) if not c1_sub.empty else np.nan
                c2_val = round(float(c2_sub['rate'].mean()), 1) if not c2_sub.empty else np.nan

        if pd.isna(c_val) and st_arr is not None:
            rst = runs_st[i]
            ret = runs_et[i]
            rmd = runs_md[i]
            dur_h1 = (rmd - rst) / 60000.0
            dur_h2 = (ret - rmd) / 60000.0

            idx_lo = np.searchsorted(st_arr, rst - 600000, side='left')
            idx_hi = np.searchsorted(st_arr, ret, side='right')
            if idx_hi > idx_lo:
                c_st = st_arr[idx_lo:idx_hi]
                c_et = et_arr[idx_lo:idx_hi]
                c_app = app_arr[idx_lo:idx_hi]
                c_cnt = cnt_arr[idx_lo:idx_hi]

                mask = (c_et >= rst) & (c_st <= ret)
                if np.any(mask):
                    m_app = c_app[mask]
                    m_cnt = c_cnt[mask]
                    m_st = c_st[mask]
                    m_et = c_et[mask]

                    run_app = runs.iloc[i].get('app_info_id', None)
                    unique_apps = np.unique(m_app)
                    if run_app in unique_apps:
                        chosen_app = run_app
                    else:
                        app_sums = {a: m_cnt[m_app == a].sum() for a in unique_apps}
                        chosen_app = max(app_sums, key=app_sums.get)

                    app_mask = (m_app == chosen_app)
                    sel_cnt = m_cnt[app_mask]
                    sel_mids = (m_st[app_mask] + m_et[app_mask]) / 2.0

                    tot_steps = sel_cnt.sum()
                    h1_steps = sel_cnt[sel_mids < rmd].sum()
                    h2_steps = sel_cnt[sel_mids >= rmd].sum()

                    c_val = round(float(tot_steps) / dur_min, 1) if dur_min > 0 else np.nan
                    c1_val = round(float(h1_steps) / dur_h1, 1) if dur_h1 > 0 else np.nan
                    c2_val = round(float(h2_steps) / dur_h2, 1) if dur_h2 > 0 else np.nan

        cad_list.append(c_val)
        cad1_list.append(c1_val)
        cad2_list.append(c2_val)

    runs['cadence'] = cad_list
    runs['cadence1'] = cad1_list
    runs['cadence2'] = cad2_list

    if hr_df is not None and not hr_df.empty:
        idx_vals = hr_df.index.values
        bpm_vals = hr_df['beats_per_minute'].values
        starts = np.searchsorted(idx_vals, runs['start_dt'].values, side='left')
        mids = np.searchsorted(idx_vals, runs['mid_dt'].values, side='right')
        ends = np.searchsorted(idx_vals, runs['end_dt'].values, side='right')

        if speed_df is not None and not speed_df.empty:
            sp_idx = speed_df.index.values
            sp_val = speed_df['speed'].values
            sp_starts = np.searchsorted(sp_idx, runs['start_dt'].values, side='left')
            sp_mids = np.searchsorted(sp_idx, runs['mid_dt'].values, side='right')
            sp_ends = np.searchsorted(sp_idx, runs['end_dt'].values, side='right')
        else:
            sp_val = None

        avg_bpms = []
        max_bpms = []
        min_bpms = []
        ef_list = []
        drift_list = []
        hr1_list = []
        hr2_list = []
        speed1_list = []
        speed2_list = []
        ef1_list = []
        ef2_list = []

        for i in range(len(runs)):
            st, md, et = starts[i], mids[i], ends[i]
            dur_min = runs.iloc[i]['duration_min']
            dist_m = runs.iloc[i]['distance_meters']

            if et > st:
                sub = bpm_vals[st:et]
                avg_hr = round(float(sub.mean()), 1)
                max_hr = int(sub.max())
                min_hr = int(sub.min())
            else:
                avg_hr = np.nan
                max_hr = np.nan
                min_hr = np.nan
            avg_bpms.append(avg_hr)
            max_bpms.append(max_hr)
            min_bpms.append(min_hr)

            # Efficiency Factor (EF) = (Speed in m/min) / (Avg HR in bpm)
            if pd.notna(dist_m) and dist_m > 0 and dur_min > 0 and pd.notna(avg_hr) and avg_hr > 0:
                speed_m_min = dist_m / dur_min
                ef = round(speed_m_min / avg_hr, 3)
            else:
                speed_m_min = np.nan
                ef = np.nan
            ef_list.append(ef)

            # Aerobic Decoupling (Cardiac Drift %) across two halves
            h1_hr = float(bpm_vals[st:md].mean()) if md > st else np.nan
            h2_hr = float(bpm_vals[md:et].mean()) if et > md else np.nan
            hr1_list.append(round(h1_hr, 1) if pd.notna(h1_hr) else np.nan)
            hr2_list.append(round(h2_hr, 1) if pd.notna(h2_hr) else np.nan)

            if sp_val is not None and sp_mids[i] > sp_starts[i] and sp_ends[i] > sp_mids[i]:
                # speed in m/s -> m/min
                speed1_m_min = float(sp_val[sp_starts[i]:sp_mids[i]].mean()) * 60.0
                speed2_m_min = float(sp_val[sp_mids[i]:sp_ends[i]].mean()) * 60.0
            elif pd.notna(speed_m_min) and speed_m_min > 0:
                speed1_m_min = speed_m_min
                speed2_m_min = speed_m_min
            else:
                speed1_m_min = np.nan
                speed2_m_min = np.nan

            sp1_kmh = round(speed1_m_min * 0.06, 1) if pd.notna(speed1_m_min) else np.nan
            sp2_kmh = round(speed2_m_min * 0.06, 1) if pd.notna(speed2_m_min) else np.nan
            speed1_list.append(sp1_kmh)
            speed2_list.append(sp2_kmh)

            if pd.notna(speed1_m_min) and pd.notna(h1_hr) and h1_hr > 0 and speed1_m_min > 0:
                ef1 = speed1_m_min / h1_hr
                ef1_val = round(ef1, 3)
            else:
                ef1 = np.nan
                ef1_val = np.nan

            if pd.notna(speed2_m_min) and pd.notna(h2_hr) and h2_hr > 0 and speed2_m_min > 0:
                ef2 = speed2_m_min / h2_hr
                ef2_val = round(ef2, 3)
            else:
                ef2 = np.nan
                ef2_val = np.nan

            if pd.notna(ef1) and pd.notna(ef2) and ef1 > 0:
                drift = round((1.0 - (ef2 / ef1)) * 100.0, 1)
            else:
                drift = np.nan

            drift_list.append(drift)
            ef1_list.append(ef1_val)
            ef2_list.append(ef2_val)

        runs['avg_bpm'] = avg_bpms
        runs['max_bpm'] = max_bpms
        runs['min_bpm'] = min_bpms
        runs['ef'] = ef_list
        runs['drift_pct'] = drift_list
        runs['hr1'] = hr1_list
        runs['hr2'] = hr2_list
        runs['speed1_kmh'] = speed1_list
        runs['speed2_kmh'] = speed2_list
        runs['ef1'] = ef1_list
        runs['ef2'] = ef2_list
        runs['stride_m'] = np.where(
            pd.notna(runs['cadence']) & (runs['cadence'] > 0),
            np.round((runs['distance_meters'] / runs['duration_min']) / runs['cadence'], 2),
            np.nan
        )
        runs['stride1_m'] = np.where(
            pd.notna(runs['cadence1']) & (runs['cadence1'] > 0) & pd.notna(runs['speed1_kmh']),
            np.round((runs['speed1_kmh'] * 1000.0 / 60.0) / runs['cadence1'], 2),
            np.nan
        )
        runs['stride2_m'] = np.where(
            pd.notna(runs['cadence2']) & (runs['cadence2'] > 0) & pd.notna(runs['speed2_kmh']),
            np.round((runs['speed2_kmh'] * 1000.0 / 60.0) / runs['cadence2'], 2),
            np.nan
        )
    else:
        runs['avg_bpm'] = np.nan
        runs['max_bpm'] = np.nan
        runs['min_bpm'] = np.nan
        runs['ef'] = np.nan
        runs['drift_pct'] = np.nan
        runs['hr1'] = np.nan
        runs['hr2'] = np.nan
        runs['speed1_kmh'] = np.nan
        runs['speed2_kmh'] = np.nan
        runs['ef1'] = np.nan
        runs['ef2'] = np.nan
        runs['stride_m'] = np.where(
            pd.notna(runs['cadence']) & (runs['cadence'] > 0),
            np.round((runs['distance_meters'] / runs['duration_min']) / runs['cadence'], 2),
            np.nan
        )
        runs['stride1_m'] = np.nan
        runs['stride2_m'] = np.nan

    return runs

def calculate_averages(df):
    """Calculates daily, weekly, and monthly averages, excluding incomplete current periods."""
    # Hierarchical resampling (Minute -> Hour -> Day -> Week/Month) to prevent sampling bias
    # from high-frequency bursts (e.g. workouts) or unequal day/night sampling rates.
    # '1min' = 1-Minute buckets, '1h' = 1-Hour buckets, 'D' = Day, 'W' = Week (ending Sunday), 'MS' = Month Start
    # .dropna() removes periods with no data
    min_avg = df.resample('1min').mean().dropna()
    hourly_avg = min_avg.resample('1h').mean().dropna()
    daily_avg = hourly_avg.resample('D').mean().dropna()
    weekly_avg = daily_avg.resample('W').mean().dropna()
    monthly_avg = daily_avg.resample('MS').mean().dropna()
    
    # Exclude incomplete periods at the end of the database export
    latest_timestamp = df.index.max()
    daily_avg = daily_avg[daily_avg.index + pd.Timedelta(days=1) <= latest_timestamp]
    weekly_avg = weekly_avg[weekly_avg.index + pd.Timedelta(days=1) <= latest_timestamp]
    monthly_avg = monthly_avg[monthly_avg.index + pd.DateOffset(months=1) <= latest_timestamp]

    return daily_avg, weekly_avg, monthly_avg

def output_console(daily, weekly, monthly, runs=None):
    """Prints the calculated averages and running sessions to the console."""
    pd.set_option('display.float_format', '{:.1f}'.format)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    
    print("\n--- Monthly Average Heart Rate ---")
    # Format index to show just 'Year-Month'
    monthly_out = monthly.copy()
    monthly_out.index = monthly_out.index.strftime('%Y-%m')
    print(monthly_out)
    
    print("\n--- Weekly Average Heart Rate ---")
    # Format index to show 'Year-Week'
    weekly_out = weekly.copy()
    weekly_out.index = weekly_out.index.strftime('%Y - Week %W')
    print(weekly_out)
    
    print("\n--- Daily Average Heart Rate ---")
    daily_out = daily.copy()
    daily_out.index = daily_out.index.strftime('%Y-%m-%d')
    print(daily_out)

    if runs is not None and not runs.empty:
        print("\n--- Running Sessions ---")
        runs_display = runs.copy()
        runs_display['Date'] = runs_display['start_dt'].dt.strftime('%Y-%m-%d %H:%M')
        runs_display['Pace'] = runs_display['pace_min_km'].apply(format_pace)
        runs_display['EF'] = runs_display['ef'].map(lambda v: f"{v:.3f}" if pd.notna(v) else "-")
        runs_display['Drift (%)'] = runs_display['drift_pct'].map(lambda v: f"{v:+.1f}%" if pd.notna(v) else "-")
        runs_display['HR H1'] = runs_display['hr1'].map(lambda v: f"{v:.1f}" if pd.notna(v) else "-")
        runs_display['HR H2'] = runs_display['hr2'].map(lambda v: f"{v:.1f}" if pd.notna(v) else "-")
        runs_display['Speed H1'] = runs_display['speed1_kmh'].map(lambda v: f"{v:.1f}" if pd.notna(v) else "-")
        runs_display['Speed H2'] = runs_display['speed2_kmh'].map(lambda v: f"{v:.1f}" if pd.notna(v) else "-")
        runs_display['Kadenz (spm)'] = runs_display['cadence'].map(lambda v: f"{v:.1f}" if pd.notna(v) else "-")
        runs_display['Kad. H1'] = runs_display['cadence1'].map(lambda v: f"{v:.1f}" if pd.notna(v) else "-")
        runs_display['Kad. H2'] = runs_display['cadence2'].map(lambda v: f"{v:.1f}" if pd.notna(v) else "-")
        runs_display['Schrittlänge (m)'] = runs_display['stride_m'].map(lambda v: f"{v:.2f}" if pd.notna(v) else "-")
        runs_display['Schrittl. H1'] = runs_display['stride1_m'].map(lambda v: f"{v:.2f}" if pd.notna(v) else "-")
        runs_display['Schrittl. H2'] = runs_display['stride2_m'].map(lambda v: f"{v:.2f}" if pd.notna(v) else "-")
        runs_display['EF H1'] = runs_display['ef1'].map(lambda v: f"{v:.3f}" if pd.notna(v) else "-")
        runs_display['EF H2'] = runs_display['ef2'].map(lambda v: f"{v:.3f}" if pd.notna(v) else "-")
        table = runs_display[[
            'Date', 'duration_min', 'distance_km', 'Pace', 'speed_kmh', 'Speed H1', 'Speed H2',
            'avg_bpm', 'max_bpm', 'HR H1', 'HR H2',
            'Kadenz (spm)', 'Kad. H1', 'Kad. H2',
            'Schrittlänge (m)', 'Schrittl. H1', 'Schrittl. H2',
            'EF', 'EF H1', 'EF H2', 'Drift (%)'
        ]].rename(columns={
            'duration_min': 'Duration (min)',
            'distance_km': 'Distance (km)',
            'speed_kmh': 'Speed (km/h)',
            'Speed H1': 'Speed H1 (km/h)',
            'Speed H2': 'Speed H2 (km/h)',
            'avg_bpm': 'Avg BPM',
            'max_bpm': 'Max BPM'
        }).set_index('Date')
        print(table)

def output_graph(daily, weekly, monthly, runs=None):
    """Displays an interactive graph of heart rate averages and running sessions in a tabbed view with data tables using Bokeh."""
    print("Generating interactive graph...")

    # --- TAB 1: Heart Rate Averages ---
    daily_df = daily.reset_index().rename(columns={'epoch_millis': 'date', 'beats_per_minute': 'bpm'})
    daily_df['date_str'] = daily_df['date'].dt.strftime('%Y-%m-%d')
    daily_source = ColumnDataSource(daily_df)
    
    weekly_df = weekly.reset_index().rename(columns={'epoch_millis': 'date', 'beats_per_minute': 'bpm'})
    weekly_df['date_str'] = weekly_df['date'].dt.strftime('%Y - Week %W (ending %Y-%m-%d)')
    weekly_source = ColumnDataSource(weekly_df)
    
    monthly_df = monthly.reset_index().rename(columns={'epoch_millis': 'date', 'beats_per_minute': 'bpm'})
    monthly_df['date_str'] = monthly_df['date'].dt.strftime('%Y-%m')
    monthly_source = ColumnDataSource(monthly_df)

    hover_avg = HoverTool(tooltips=[
        ("Type", "$name"),
        ("Date", "@date_str"),
        ("Avg BPM", "@bpm{0.1f}"),
    ])

    p_avg = figure(
        title="Average Heart Rate Over Time",
        x_axis_label='Date',
        y_axis_label='Beats Per Minute (BPM)',
        x_axis_type="datetime",
        sizing_mode='stretch_width',
        height=450,
        tools="pan,wheel_zoom,box_zoom,reset,save"
    )

    r_daily_line = p_avg.line(x='date', y='bpm', source=daily_source, legend_label="Daily Avg", color="green", line_dash="dotted", line_width=1, name="Daily Average")
    r_daily_pts = p_avg.scatter(x='date', y='bpm', source=daily_source, legend_label="Daily Avg", color="green", size=3, alpha=0.5, name="Daily Average")

    r_weekly_line = p_avg.line(x='date', y='bpm', source=weekly_source, legend_label="Weekly Avg", color="orange", line_dash="dashed", line_width=2, name="Weekly Average")
    r_weekly_pts = p_avg.scatter(x='date', y='bpm', source=weekly_source, legend_label="Weekly Avg", color="orange", size=5, name="Weekly Average")

    r_monthly_line = p_avg.line(x='date', y='bpm', source=monthly_source, legend_label="Monthly Avg", color="red", line_width=3, name="Monthly Average")
    r_monthly_pts = p_avg.scatter(x='date', y='bpm', source=monthly_source, legend_label="Monthly Avg", color="red", size=7, name="Monthly Average")

    hover_avg.renderers = [r_daily_line, r_daily_pts, r_weekly_line, r_weekly_pts, r_monthly_line, r_monthly_pts]
    p_avg.add_tools(hover_avg)

    p_avg.legend.location = "top_left"
    p_avg.legend.click_policy = "hide"

    # Data tables for averages
    tbl_cols_m = [
        TableColumn(field='date_str', title='Month', width=180),
        TableColumn(field='bpm', title='Avg BPM', formatter=NumberFormatter(format='0.0'), width=120)
    ]
    tbl_monthly = DataTable(source=monthly_source, columns=tbl_cols_m, sizing_mode='stretch_width', height=220)

    tbl_cols_w = [
        TableColumn(field='date_str', title='Week', width=260),
        TableColumn(field='bpm', title='Avg BPM', formatter=NumberFormatter(format='0.0'), width=120)
    ]
    tbl_weekly = DataTable(source=weekly_source, columns=tbl_cols_w, sizing_mode='stretch_width', height=220)

    tbl_cols_d = [
        TableColumn(field='date_str', title='Date', width=180),
        TableColumn(field='bpm', title='Avg BPM', formatter=NumberFormatter(format='0.0'), width=120)
    ]
    tbl_daily = DataTable(source=daily_source, columns=tbl_cols_d, sizing_mode='stretch_width', height=220)

    avg_tables_tabs = Tabs(tabs=[
        TabPanel(child=tbl_monthly, title="Monthly"),
        TabPanel(child=tbl_weekly, title="Weekly"),
        TabPanel(child=tbl_daily, title="Daily")
    ], sizing_mode='stretch_width')

    tab_avg = TabPanel(child=column(p_avg, avg_tables_tabs, sizing_mode='stretch_width'), title="Heart Rate Averages")

    # --- TAB 2: Running Sessions & Efficiency ---
    if runs is not None and not runs.empty:
        runs_plot_df = runs.copy()
        if not runs_plot_df.empty:
            runs_plot_df['date'] = runs_plot_df['start_dt']
            runs_plot_df['date_str'] = runs_plot_df['start_dt'].dt.strftime('%Y-%m-%d %H:%M')
            runs_plot_df['ef_str'] = runs_plot_df['ef'].map(lambda v: f"{v:.3f}" if pd.notna(v) else "-")
            runs_plot_df['ef1_str'] = runs_plot_df['ef1'].map(lambda v: f"{v:.3f}" if pd.notna(v) else "-")
            runs_plot_df['ef2_str'] = runs_plot_df['ef2'].map(lambda v: f"{v:.3f}" if pd.notna(v) else "-")
            runs_plot_df['drift_str'] = runs_plot_df['drift_pct'].map(lambda v: f"{v:+.1f}%" if pd.notna(v) else "-")
            runs_plot_df['pace_str'] = runs_plot_df['pace_min_km'].map(format_pace)
            runs_plot_df['speed_str'] = runs_plot_df['speed_kmh'].map(lambda s: f"{s:.1f} km/h" if pd.notna(s) else "-")
            runs_plot_df['speed1_str'] = runs_plot_df['speed1_kmh'].map(lambda s: f"{s:.1f} km/h" if pd.notna(s) else "-")
            runs_plot_df['speed2_str'] = runs_plot_df['speed2_kmh'].map(lambda s: f"{s:.1f} km/h" if pd.notna(s) else "-")
            runs_plot_df['distance_str'] = runs_plot_df['distance_km'].map(lambda d: f"{d:.2f} km" if pd.notna(d) else "-")
            runs_plot_df['duration_str'] = runs_plot_df['duration_min'].map(lambda d: f"{d:.1f} min")
            runs_plot_df['avg_bpm_str'] = runs_plot_df['avg_bpm'].map(lambda b: f"{b:.1f} BPM" if pd.notna(b) else "-")
            runs_plot_df['max_bpm_str'] = runs_plot_df['max_bpm'].map(lambda b: f"{int(b)} BPM" if pd.notna(b) else "-")
            runs_plot_df['cadence_str'] = runs_plot_df['cadence'].map(lambda c: f"{c:.1f} SPM" if pd.notna(c) else "-")
            runs_plot_df['cad1_str'] = runs_plot_df['cadence1'].map(lambda c: f"{c:.1f}" if pd.notna(c) else "-")
            runs_plot_df['cad2_str'] = runs_plot_df['cadence2'].map(lambda c: f"{c:.1f}" if pd.notna(c) else "-")
            runs_plot_df['cad_splits_str'] = runs_plot_df.apply(
                lambda r: f"H1: {r['cadence1']:.1f} / H2: {r['cadence2']:.1f} SPM" if pd.notna(r['cadence1']) and pd.notna(r['cadence2']) else "-",
                axis=1
            )
            runs_plot_df['stride_str'] = runs_plot_df['stride_m'].map(lambda s: f"{s:.2f} m" if pd.notna(s) else "-")
            runs_plot_df['stride1_str'] = runs_plot_df['stride1_m'].map(lambda s: f"{s:.2f} m" if pd.notna(s) else "-")
            runs_plot_df['stride2_str'] = runs_plot_df['stride2_m'].map(lambda s: f"{s:.2f} m" if pd.notna(s) else "-")
            runs_plot_df['stride_splits_str'] = runs_plot_df.apply(
                lambda r: f"H1: {r['stride1_m']:.2f} / H2: {r['stride2_m']:.2f} m" if pd.notna(r['stride1_m']) and pd.notna(r['stride2_m']) else "-",
                axis=1
            )
            runs_plot_df['hr_splits_str'] = runs_plot_df.apply(
                lambda r: f"H1: {r['hr1']:.0f} / H2: {r['hr2']:.0f} BPM" if pd.notna(r['hr1']) and pd.notna(r['hr2']) else "-",
                axis=1
            )
            runs_plot_df['ef_splits_str'] = runs_plot_df.apply(
                lambda r: f"H1: {r['ef1']:.3f} / H2: {r['ef2']:.3f}" if pd.notna(r['ef1']) and pd.notna(r['ef2']) else "-",
                axis=1
            )
            runs_plot_df['speed_splits_str'] = runs_plot_df.apply(
                lambda r: f"H1: {r['speed1_kmh']:.1f} / H2: {r['speed2_kmh']:.1f} km/h" if pd.notna(r['speed1_kmh']) and pd.notna(r['speed2_kmh']) else "-",
                axis=1
            )

            runs_source = ColumnDataSource(runs_plot_df)

            # Top plot: Efficiency Factor (EF)
            p_ef = figure(
                title="Running Efficiency Factor (EF = Speed in m/min / Avg BPM) Over Time",
                x_axis_label="Date",
                y_axis_label="EF (m/min / bpm)",
                x_axis_type="datetime",
                sizing_mode='stretch_width',
                height=260,
                tools="pan,wheel_zoom,box_zoom,reset,save"
            )
            p_ef.line(x='date', y='ef', source=runs_source, color="#1f77b4", line_width=2, alpha=0.8, legend_label="Efficiency Factor (EF)")
            r_ef = p_ef.scatter(x='date', y='ef', source=runs_source, color="#1f77b4", size=7, name="Run EF", legend_label="Efficiency Factor (EF)")

            hover_ef = HoverTool(
                renderers=[r_ef],
                tooltips=[
                    ("Date", "@date_str"),
                    ("Efficiency Factor (EF)", "@ef_str"),
                    ("EF Splits (H1 / H2)", "@ef_splits_str"),
                    ("Cardiac Drift", "@drift_str"),
                    ("Cadence", "@cadence_str"),
                    ("Stride Length", "@stride_str"),
                    ("Avg BPM", "@avg_bpm_str"),
                    ("HR Splits (H1 / H2)", "@hr_splits_str"),
                    ("Max BPM", "@max_bpm_str"),
                    ("Pace", "@pace_str"),
                    ("Speed", "@speed_str"),
                    ("Speed Splits (H1 / H2)", "@speed_splits_str"),
                    ("Distance", "@distance_str"),
                    ("Duration", "@duration_str"),
                ]
            )
            p_ef.add_tools(hover_ef)
            p_ef.legend.location = "top_left"
            p_ef.legend.click_policy = "hide"

            # Second plot: Aerobic Decoupling (Cardiac Drift %) sharing x_range
            p_drift = figure(
                title="Aerobic Decoupling (Cardiac Drift %) Over Time",
                x_axis_label="Date",
                y_axis_label="Drift (%)",
                x_axis_type="datetime",
                x_range=p_ef.x_range,
                sizing_mode='stretch_width',
                height=240,
                tools="pan,wheel_zoom,box_zoom,reset,save"
            )

            span_5 = Span(location=5.0, dimension='width', line_color='#e67e22', line_dash='dashed', line_width=1.5)
            span_0 = Span(location=0.0, dimension='width', line_color='#bdc3c7', line_dash='dotted', line_width=1)
            p_drift.add_layout(span_5)
            p_drift.add_layout(span_0)

            p_drift.line(x='date', y='drift_pct', source=runs_source, color="#8e44ad", line_width=2, alpha=0.8, legend_label="Cardiac Drift (%)")
            r_drift = p_drift.scatter(x='date', y='drift_pct', source=runs_source, color="#8e44ad", size=7, name="Drift", legend_label="Cardiac Drift (%)")

            hover_drift = HoverTool(
                renderers=[r_drift],
                tooltips=[
                    ("Date", "@date_str"),
                    ("Cardiac Drift", "@drift_str"),
                    ("HR Splits (H1 / H2)", "@hr_splits_str"),
                    ("Cadence", "@cadence_str"),
                    ("Stride Length", "@stride_str"),
                    ("EF Splits (H1 / H2)", "@ef_splits_str"),
                    ("Speed Splits (H1 / H2)", "@speed_splits_str"),
                    ("Efficiency Factor (EF)", "@ef_str"),
                    ("Pace", "@pace_str"),
                    ("Distance", "@distance_str"),
                    ("Duration", "@duration_str"),
                ]
            )
            p_drift.add_tools(hover_drift)
            p_drift.legend.location = "top_left"
            p_drift.legend.click_policy = "hide"

            # Third plot: Running Cadence (Steps per Minute) sharing x_range
            p_cad = figure(
                title="Running Cadence (Steps per Minute) Over Time",
                x_axis_label="Date",
                y_axis_label="Cadence (SPM)",
                x_axis_type="datetime",
                x_range=p_ef.x_range,
                sizing_mode='stretch_width',
                height=240,
                tools="pan,wheel_zoom,box_zoom,reset,save"
            )

            p_cad.line(x='date', y='cadence', source=runs_source, color="#16a085", line_width=2, alpha=0.8, legend_label="Cadence (SPM)")
            r_cad = p_cad.scatter(x='date', y='cadence', source=runs_source, color="#16a085", size=7, name="Cadence", legend_label="Cadence (SPM)")

            hover_cad = HoverTool(
                renderers=[r_cad],
                tooltips=[
                    ("Datum", "@date_str"),
                    ("Kadenz", "@cadence_str"),
                    ("Kadenz Splits (H1 / H2)", "@cad_splits_str"),
                    ("Schrittlänge", "@stride_str"),
                    ("Schrittlänge Splits (H1 / H2)", "@stride_splits_str"),
                    ("Pace", "@pace_str"),
                    ("Speed", "@speed_str"),
                    ("Distanz", "@distance_str"),
                    ("Dauer", "@duration_str"),
                    ("Avg BPM", "@avg_bpm_str"),
                ]
            )
            p_cad.add_tools(hover_cad)
            p_cad.legend.location = "top_left"
            p_cad.legend.click_policy = "hide"

            # Fourth plot: Running Stride Length (Meters) sharing x_range
            p_stride = figure(
                title="Schrittlänge (Meter) im Zeitverlauf / Running Stride Length Over Time",
                x_axis_label="Datum",
                y_axis_label="Schrittlänge (m)",
                x_axis_type="datetime",
                x_range=p_ef.x_range,
                sizing_mode='stretch_width',
                height=240,
                tools="pan,wheel_zoom,box_zoom,reset,save"
            )

            p_stride.line(x='date', y='stride_m', source=runs_source, color="#2980b9", line_width=2, alpha=0.8, legend_label="Schrittlänge (m)")
            r_stride = p_stride.scatter(x='date', y='stride_m', source=runs_source, color="#2980b9", size=7, name="Schrittlänge", legend_label="Schrittlänge (m)")

            hover_stride = HoverTool(
                renderers=[r_stride],
                tooltips=[
                    ("Datum", "@date_str"),
                    ("Schrittlänge", "@stride_str"),
                    ("Schrittlänge Splits (H1 / H2)", "@stride_splits_str"),
                    ("Kadenz", "@cadence_str"),
                    ("Pace", "@pace_str"),
                    ("Speed", "@speed_str"),
                    ("Distanz", "@distance_str"),
                    ("Dauer", "@duration_str"),
                    ("Avg BPM", "@avg_bpm_str"),
                ]
            )
            p_stride.add_tools(hover_stride)
            p_stride.legend.location = "top_left"
            p_stride.legend.click_policy = "hide"

            # Running sessions data table
            cols_runs = [
                TableColumn(field='date_str', title='Datum', width=130),
                TableColumn(field='duration_min', title='Dauer (min)', formatter=NumberFormatter(format='0.0'), width=85),
                TableColumn(field='distance_km', title='Distanz (km)', formatter=NumberFormatter(format='0.00'), width=85),
                TableColumn(field='pace_str', title='Pace', width=75),
                TableColumn(field='speed_kmh', title='Speed (km/h)', formatter=NumberFormatter(format='0.0'), width=85),
                TableColumn(field='speed1_kmh', title='Speed H1 (km/h)', formatter=NumberFormatter(format='0.0'), width=105),
                TableColumn(field='speed2_kmh', title='Speed H2 (km/h)', formatter=NumberFormatter(format='0.0'), width=105),
                TableColumn(field='avg_bpm', title='Avg BPM', formatter=NumberFormatter(format='0.0'), width=75),
                TableColumn(field='max_bpm', title='Max BPM', formatter=NumberFormatter(format='0'), width=70),
                TableColumn(field='hr1', title='HR H1', formatter=NumberFormatter(format='0.0'), width=70),
                TableColumn(field='hr2', title='HR H2', formatter=NumberFormatter(format='0.0'), width=70),
                TableColumn(field='cadence', title='Kadenz (spm)', formatter=NumberFormatter(format='0.0'), width=95),
                TableColumn(field='cadence1', title='Kad. H1', formatter=NumberFormatter(format='0.0'), width=75),
                TableColumn(field='cadence2', title='Kad. H2', formatter=NumberFormatter(format='0.0'), width=75),
                TableColumn(field='stride_m', title='Schrittlänge (m)', formatter=NumberFormatter(format='0.00'), width=115),
                TableColumn(field='stride1_m', title='Schrittl. H1', formatter=NumberFormatter(format='0.00'), width=85),
                TableColumn(field='stride2_m', title='Schrittl. H2', formatter=NumberFormatter(format='0.00'), width=85),
                TableColumn(field='ef', title='EF', formatter=NumberFormatter(format='0.000'), width=70),
                TableColumn(field='ef1', title='EF H1', formatter=NumberFormatter(format='0.000'), width=70),
                TableColumn(field='ef2', title='EF H2', formatter=NumberFormatter(format='0.000'), width=70),
                TableColumn(field='drift_pct', title='Drift (%)', formatter=NumberFormatter(format='+0.0'), width=75),
            ]
            tbl_runs = DataTable(source=runs_source, columns=cols_runs, sizing_mode='stretch_width', height=300, sortable=True)

            tab_runs = TabPanel(child=column(p_ef, p_drift, p_cad, p_stride, tbl_runs, sizing_mode='stretch_width'), title="Running Sessions")
            layout = Tabs(tabs=[tab_avg, tab_runs], sizing_mode='stretch_width')
        else:
            layout = column(p_avg, avg_tables_tabs, sizing_mode='stretch_width')
    else:
        layout = column(p_avg, avg_tables_tabs, sizing_mode='stretch_width')

    # Display the plot. Bokeh will open this in your default web browser.
    print("Opening plot in your web browser...")
    show(layout)

def main():
    """Main execution function."""
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
    
    args = parser.parse_args()
    
    conn = None
    temp_dir = None
    try:
        db_path = args.db_file
        
        if Path(db_path).is_file() and zipfile.is_zipfile(db_path):
            print("Extracting database from ZIP archive...")
            temp_dir = tempfile.TemporaryDirectory()
            with zipfile.ZipFile(db_path, 'r') as z:
                # Find the database file, prioritizing .db or .sqlite
                db_filename = next((name for name in z.namelist() if name.endswith(('.db', '.sqlite'))), None)
                if not db_filename and z.namelist():
                    db_filename = z.namelist()[0]
                
                if db_filename:
                    db_path = z.extract(db_filename, temp_dir.name)
                else:
                    print("Error: No files found in the ZIP archive.", file=sys.stderr)
                    sys.exit(1)
                    
        conn = connect_db(db_path)
        
        # --- TEMPORARY DIAGNOSTIC STEP ---
        # Run this once to see the column names, then comment out the next line.
        # inspect_table_columns(conn, 'heart_rate_record_series_table')
        # sys.exit(0) # Exit after inspecting
        # ---------------------------------

        # --- NORMAL EXECUTION (Uncomment after fixing query) ---
        df = fetch_heart_rate_data(conn)
        
        if df is None:
            sys.exit(1)
            
        latest_time = df.index[-1]
        latest_bpm = df.iloc[-1]['beats_per_minute']
        print(f"Latest heartbeat record: {latest_time.strftime('%Y-%m-%d %H:%M:%S')} ({latest_bpm} BPM)")

        runs = None
        if not args.no_runs:
            runs = fetch_running_sessions_data(conn, df)

        resting_df = df
        if args.max_bpm is not None:
            print(f"Filtering resting averages: Ignoring heart rates above {args.max_bpm} BPM.")
            resting_df = df[df['beats_per_minute'] <= args.max_bpm]

        daily, weekly, monthly = calculate_averages(resting_df)
        
        if args.output == 'console':
            output_console(daily, weekly, monthly, runs)
        elif args.output == 'graph':
            output_graph(daily, weekly, monthly, runs)
            
    finally:
        if conn:
            conn.close()
        if temp_dir:
            temp_dir.cleanup()

if __name__ == "__main__":
    main()
