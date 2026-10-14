# Android Health Connect Data Explorer

A Python script to analyze your exported Android Health Connect SQLite database, focusing on heart rate data. It calculates daily, weekly, and monthly averages and can display them in the console or as a beautiful, interactive graph.

![Demo Graph](docs/example_graph.png)

## Why?

Android's Health Connect "export data" feature gives you a raw SQLite database file, but it's not in a human-readable format. This script connects directly to that database, extracts the most useful data (your heart rate), and turns it into easy-to-understand averages.

## Features

* **Direct SQLite Connection:** Reads your `.db` export file directly.
* **Time-Series Analysis:** Parses your raw heart rate data (`heart_rate_record_series_table`).
* **Multiple Averages:** Automatically calculates daily, weekly, and monthly heart rate averages.
* **Running Sessions & Efficiency Analysis:** Automatically detects running sessions (`exercise_session_record_table`) and calculates:
    * **Efficiency Factor (EF):** $\text{Speed (m/min)} / \text{Avg BPM}$ to track aerobic economy trends over time.
    * **Aerobic Decoupling ($Pw:HR$ / Drift %):** Compares first-half vs second-half efficiency ($(1 - \text{EF}_2 / \text{EF}_1) \times 100$) with a 5% aerobic decoupling threshold.
    * **Running Cadence (SPM):** Total and split cadence (steps per minute) calculated from cadence records or step series.
    * **Stride Length (m):** Total and split stride length in meters calculated from distance and steps / cadence.
    * **Half-Split Metrics:** Heart rate, speed, cadence, stride length, and efficiency for both the first and second halves of the run.
    * Duration, distance, pace, speed, and average/max heart rate.
* **Two Output Modes:**
    * `console`: Prints clean, formatted tables of resting averages and running sessions with EF, Cardiac Drift, Cadence, and Stride Length.
    * `graph`: Generates an interactive, responsive tabbed HTML graph using [Bokeh](https://bokeh.org/) with dedicated tabs for **Heart Rate Averages** and **Running Sessions** (with synchronized time axes for EF, Cardiac Drift, Cadence, and Stride Length).
* **Data Filtering:** Use the `--max-bpm` flag to filter resting trends without affecting running session metrics, or `--no-runs` to exclude running sessions entirely.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/verybadsoldier/android-health-connect-data-explorer.git
    cd android-health-connect-data-explorer
    ```

2.  **Create a virtual environment (Recommended):**
    ```bash
    # On macOS/Linux
    python3 -m venv venv
    source venv/bin/activate
    
    # On Windows
    python -m venv venv
    .\venv\Scripts\activate
    ```

3.  **Install the required libraries:**
    ```bash
    pip install -r requirements.txt
    ```

## Usage

You will need the path to your exported Health Connect database file (e.g., `health-connect-export.db`).

### To Output Averages to the Console:

This is the default behavior.

```bash
python health_analysis.py /path/to/your/health-connect-export.db
```

### To Generate the Interactive Graph:

This will open the graph in your default web browser.

```bash
python health_analysis.py /path/to/your/health-connect-export.db --output graph
```

### To Filter Data:

Here's how to generate a graph that ignores any heart rate readings above 90 BPM.

```bash
python health_analysis.py /path/to/your/health-connect-export.db --output graph --max-bpm 90
```

---

## **Important: Database Schema**

This script is built assuming the heart rate data is in `heart_rate_record_series_table` with the following columns:

* **Timestamp column:** `epoch_millis`
* **Heart rate column:** `beats_per_minute`

If your database export has a different structure, the script will likely fail. If this happens, you will need to edit the `sql_query` variable inside the `fetch_heart_rate_data` function in `health_analysis.py` to match your schema.

A helper function `inspect_table_columns` is included in the script (commented out in `main()`) which you can use to help find the correct column names if needed.

## License

This project is licensed under the MIT License. (You can add a `LICENSE` file to your repo by clicking "Add file" > "Create new file" on your repo's main page. Type `LICENSE` as the filename and GitHub will offer you an MIT template.)
