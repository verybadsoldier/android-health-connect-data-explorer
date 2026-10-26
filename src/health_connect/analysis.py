"""
Health metrics analytics: hierarchical resting averages, running efficiency,
aerobic decoupling (cardiac drift), cadence, and stride length calculations.
"""

import numpy as np
import pandas as pd


def format_pace(p: float | None) -> str:
    """Formats numeric pace (minutes per km) as MM:SS min/km."""
    if pd.isna(p) or p <= 0 or p > 30:
        return "-"
    mins = int(p)
    secs = int(round((p - mins) * 60))
    if secs == 60:
        mins += 1
        secs = 0
    return f"{mins}:{secs:02d} min/km"


def calculate_averages(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Calculates daily, weekly, and monthly averages using hierarchical resampling,
    excluding incomplete periods at the end of the recording.
    """
    # Hierarchical resampling (Minute -> Hour -> Day -> Week/Month) to prevent sampling bias
    # from high-frequency bursts (e.g. workouts) or unequal day/night sampling rates.
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


def calculate_running_metrics(
    runs: pd.DataFrame,
    hr_df: pd.DataFrame | None = None,
    speed_df: pd.DataFrame | None = None,
    cadence_df: pd.DataFrame | None = None,
    steps_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Calculates running metrics (speed, cadence, efficiency factor, cardiac drift,
    stride length, and split metrics) across all running sessions.
    """
    runs = runs.copy()
    runs['start_dt'] = pd.to_datetime(runs['start_time'], unit='ms')
    runs['end_dt'] = pd.to_datetime(runs['end_time'], unit='ms')
    if 'pause_ms' not in runs.columns:
        runs['pause_ms'] = 0
    runs['total_duration_min'] = (runs['end_time'] - runs['start_time']) / 1000.0 / 60.0
    runs['pause_min'] = runs['pause_ms'] / 1000.0 / 60.0
    runs['duration_min'] = np.where(
        (runs['pause_min'] > 0) & (runs['total_duration_min'] > runs['pause_min']),
        runs['total_duration_min'] - runs['pause_min'],
        runs['total_duration_min']
    )
    if 'pause_h1_ms' in runs.columns and 'pause_h2_ms' in runs.columns:
        runs['pause_h1_min'] = runs['pause_h1_ms'] / 1000.0 / 60.0
        runs['pause_h2_min'] = runs['pause_h2_ms'] / 1000.0 / 60.0
    else:
        runs['pause_h1_min'] = np.where(runs['pause_min'] > 0, runs['pause_min'] / 2.0, 0.0)
        runs['pause_h2_min'] = np.where(runs['pause_min'] > 0, runs['pause_min'] / 2.0, 0.0)
    runs['distance_km'] = runs['distance_meters'] / 1000.0
    runs['pace_min_km'] = runs['duration_min'] / runs['distance_km']
    runs['speed_kmh'] = runs['distance_km'] / (runs['duration_min'] / 60.0)
    runs['mid_dt'] = runs['start_dt'] + (runs['end_dt'] - runs['start_dt']) / 2

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
            p_h1 = runs['pause_h1_min'].iloc[i]
            p_h2 = runs['pause_h2_min'].iloc[i]
            tot_dur_h1 = (rmd - rst) / 60000.0
            tot_dur_h2 = (ret - rmd) / 60000.0
            dur_h1 = max(0.001, tot_dur_h1 - p_h1) if p_h1 < tot_dur_h1 else tot_dur_h1
            dur_h2 = max(0.001, tot_dur_h2 - p_h2) if p_h2 < tot_dur_h2 else tot_dur_h2

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
