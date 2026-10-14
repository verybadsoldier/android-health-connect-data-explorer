"""
Visualization components: console summary tables and interactive Bokeh graphs.
"""

from bokeh.layouts import column
from bokeh.models import ColumnDataSource, DataTable, HoverTool, NumberFormatter, Span, TableColumn, TabPanel, Tabs
from bokeh.plotting import figure, show
import pandas as pd

from .analysis import format_pace


def build_heart_rate_tab(
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    monthly: pd.DataFrame
) -> TabPanel:
    """Creates the Bokeh TabPanel for Heart Rate Averages (plot and data tables)."""
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

    return TabPanel(
        child=column(p_avg, avg_tables_tabs, sizing_mode='stretch_width'),
        title="Heart Rate Averages"
    )


def build_running_tab(runs: pd.DataFrame) -> TabPanel:
    """Creates the Bokeh TabPanel for Running Sessions (EF, Drift, Cadence, Stride plots and table)."""
    runs_plot_df = runs.copy()
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

    # Plot 1: Efficiency Factor (EF)
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

    # Plot 2: Aerobic Decoupling (Cardiac Drift %) sharing x_range
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

    # Plot 3: Running Cadence (Steps per Minute) sharing x_range
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

    # Plot 4: Running Stride Length (Meters) sharing x_range
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

    return TabPanel(
        child=column(p_ef, p_drift, p_cad, p_stride, tbl_runs, sizing_mode='stretch_width'),
        title="Running Sessions"
    )


def output_console(
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    monthly: pd.DataFrame,
    runs: pd.DataFrame | None = None
) -> None:
    """Prints the calculated averages and running sessions to the console."""
    pd.set_option('display.float_format', '{:.1f}'.format)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)

    print("\n--- Monthly Average Heart Rate ---")
    monthly_out = monthly.copy()
    monthly_out.index = monthly_out.index.strftime('%Y-%m')
    print(monthly_out)

    print("\n--- Weekly Average Heart Rate ---")
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


def output_graph(
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    monthly: pd.DataFrame,
    runs: pd.DataFrame | None = None
) -> None:
    """
    Displays an interactive graph of heart rate averages and running sessions
    in a tabbed view with data tables using Bokeh.
    """
    print("Generating interactive graph...")
    tab_avg = build_heart_rate_tab(daily, weekly, monthly)

    if runs is not None and not runs.empty:
        tab_runs = build_running_tab(runs)
        layout = Tabs(tabs=[tab_avg, tab_runs], sizing_mode='stretch_width')
    else:
        layout = tab_avg.child

    print("Opening plot in your web browser...")
    show(layout)
