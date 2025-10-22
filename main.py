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
from bokeh.plotting import figure, show
from bokeh.models import HoverTool, ColumnDataSource
import argparse
import sys
from pathlib import Path

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

def calculate_averages(df):
    """Calculates daily, weekly, and monthly averages."""
    # Resample data into different time bins and calculate the mean
    # 'D' = Day, 'W' = Week (ending on Sunday), 'ME' = Month End
    # .dropna() removes periods with no data
    daily_avg = df.resample('D').mean().dropna()
    weekly_avg = df.resample('W').mean().dropna()
    monthly_avg = df.resample('ME').mean().dropna()
    
    return daily_avg, weekly_avg, monthly_avg

def output_console(daily, weekly, monthly):
    """Prints the calculated averages to the console."""
    pd.set_option('display.float_format', '{:.1f}'.format)
    
    print("\n--- Monthly Average Heart Rate ---")
    # Format index to show just 'Year-Month'
    monthly.index = monthly.index.strftime('%Y-%m')
    print(monthly)
    
    print("\n--- Weekly Average Heart Rate ---")
    # Format index to show 'Year-Week'
    weekly.index = weekly.index.strftime('%Y - Week %U')
    print(weekly)
    
    print("\n--- Daily Average Heart Rate ---")
    daily.index = daily.index.strftime('%Y-%m-%d')
    print(daily)

def output_graph(daily, weekly, monthly):
    """Displays an interactive graph of the heart rate averages using Bokeh."""
    print("Generating interactive graph...")

    # Bokeh works best with ColumnDataSource. Let's prepare the data.
    # We need to reset the index to use the dates as a standard column.
    # If your time column is different, update it here too.
    daily_source = ColumnDataSource(daily.reset_index().rename(columns={'epoch_millis': 'date', 'beats_per_minute': 'bpm'}))
    weekly_source = ColumnDataSource(weekly.reset_index().rename(columns={'epoch_millis': 'date', 'beats_per_minute': 'bpm'}))
    monthly_source = ColumnDataSource(monthly.reset_index().rename(columns={'epoch_millis': 'date', 'beats_per_minute': 'bpm'}))

    # Define the tooltips for the hover tool
    tooltips = [
        ("Date", "@date{%F}"),  # Format date as YYYY-MM-DD
        ("Avg BPM", "@bpm{0.1f}"), # Format BPM to one decimal place
    ]

    # Create a HoverTool instance
    hover = HoverTool(
        tooltips=tooltips,
        formatters={'@date': 'datetime'} # Tell HoverTool the 'date' column is datetime
    )

    # Create a new plot with a datetime x-axis
    p = figure(
        title="Average Heart Rate Over Time",
        x_axis_label='Date',
        y_axis_label='Beats Per Minute (BPM)',
        x_axis_type="datetime",
        width=1000,
        height=500,
        tools="pan,wheel_zoom,box_zoom,reset,save" # Add interactive tools
    )
    
    # Add the hover tool to the plot
    p.add_tools(hover)

    # Add renderers for each data series
    p.line(x='date', y='bpm', source=daily_source, legend_label="Daily Avg", color="green", line_dash="dotted", line_width=1)
    p.circle(x='date', y='bpm', source=daily_source, legend_label="Daily Avg", color="green", size=3, alpha=0.5)

    p.line(x='date', y='bpm', source=weekly_source, legend_label="Weekly Avg", color="orange", line_dash="dashed", line_width=2)
    p.circle(x='date', y='bpm', source=weekly_source, legend_label="Weekly Avg", color="orange", size=5)

    p.line(x='date', y='bpm', source=monthly_source, legend_label="Monthly Avg", color="red", line_width=3)
    p.circle(x='date', y='bpm', source=monthly_source, legend_label="Monthly Avg", color="red", size=7)

    # Customize legend
    p.legend.location = "top_left"
    p.legend.click_policy = "hide"  # Click to hide series

    # Display the plot. Bokeh will open this in your default web browser.
    print("Opening plot in your web browser...")
    show(p)

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Analyze Android Health Connect heart rate data."
    )
    parser.add_argument(
        "db_file",
        type=str,
        help="Path to the Health Connect SQLite database file."
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
    
    args = parser.parse_args()
    
    conn = None
    try:
        conn = connect_db(args.db_file)
        
        # --- TEMPORARY DIAGNOSTIC STEP ---
        # Run this once to see the column names, then comment out the next line.
        # inspect_table_columns(conn, 'heart_rate_record_series_table')
        # sys.exit(0) # Exit after inspecting
        # ---------------------------------

        # --- NORMAL EXECUTION (Uncomment after fixing query) ---
        # Pass the max_bpm argument to the fetch function
        df = fetch_heart_rate_data(conn, args.max_bpm)
        
        if df is None:
            sys.exit(1)
            
        daily, weekly, monthly = calculate_averages(df)
        
        if args.output == 'console':
            output_console(daily, weekly, monthly)
        elif args.output == 'graph':
            output_graph(daily, weekly, monthly)
            
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()




