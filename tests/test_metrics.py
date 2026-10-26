import unittest
import numpy as np
import pandas as pd
from health_connect.analysis import calculate_averages, calculate_running_metrics, format_pace


class TestHealthConnectMetrics(unittest.TestCase):
    def test_format_pace(self):
        self.assertEqual(format_pace(5.5), "5:30 min/km")
        self.assertEqual(format_pace(6.0), "6:00 min/km")
        self.assertEqual(format_pace(4.999), "5:00 min/km")
        self.assertEqual(format_pace(None), "-")
        self.assertEqual(format_pace(np.nan), "-")
        self.assertEqual(format_pace(0), "-")
        self.assertEqual(format_pace(35.0), "-")

    def test_calculate_averages(self):
        # 3 days of minute-level records
        dates = pd.date_range("2026-01-01 00:00:00", "2026-01-03 12:00:00", freq="1min")
        df = pd.DataFrame({"beats_per_minute": [70.0] * len(dates)}, index=dates)

        daily, weekly, monthly = calculate_averages(df)

        # Incomplete end period (Jan 3 afternoon to midnight) excluded
        self.assertTrue((daily["beats_per_minute"] == 70.0).all())
        self.assertIn(pd.Timestamp("2026-01-01"), daily.index)
        self.assertIn(pd.Timestamp("2026-01-02"), daily.index)
        # Jan 3 should not be in daily because Jan 3 + 1 day > latest timestamp (Jan 3 12:00)
        self.assertNotIn(pd.Timestamp("2026-01-03"), daily.index)

    def test_calculate_running_metrics(self):
        # Run from 10:00 to 10:30 (30 min, 5000 m = 5 km)
        st = pd.Timestamp("2026-06-01 10:00:00").value // 10**6
        et = pd.Timestamp("2026-06-01 10:30:00").value // 10**6
        runs = pd.DataFrame([{
            "row_id": 1,
            "app_info_id": 1,
            "start_time": st,
            "end_time": et,
            "exercise_type": 33,
            "title": "Running",
            "distance_meters": 5000.0,
            "pause_ms": 0,
        }])

        # HR series: H1 (10:00-10:15) avg 140 bpm, H2 (10:15-10:30) avg 150 bpm
        hr_dates = pd.date_range("2026-06-01 10:00:00", "2026-06-01 10:30:00", freq="1s")
        hr_values = [140.0 if t < pd.Timestamp("2026-06-01 10:15:00") else 150.0 for t in hr_dates]
        hr_df = pd.DataFrame({"beats_per_minute": hr_values}, index=hr_dates)

        # Cadence series: 160 spm
        cad_dates = pd.date_range("2026-06-01 10:00:00", "2026-06-01 10:30:00", freq="1min")
        cad_df = pd.DataFrame({"rate": [160.0] * len(cad_dates)}, index=cad_dates)

        res = calculate_running_metrics(runs, hr_df=hr_df, cadence_df=cad_df)

        row = res.iloc[0]
        self.assertEqual(row["duration_min"], 30.0)
        self.assertEqual(row["distance_km"], 5.0)
        self.assertEqual(row["speed_kmh"], 10.0)
        self.assertEqual(row["pace_min_km"], 6.0)
        self.assertEqual(row["cadence"], 160.0)

        # Speed = 5000m / 30min = 166.667 m/min
        # Avg HR ~ 145 bpm -> EF ~ 166.667 / 145 = 1.15
        self.assertAlmostEqual(row["ef"], 166.667 / row["avg_bpm"], places=2)

        # Drift = (1 - EF2 / EF1) * 100
        # EF1 = speed / 140, EF2 = speed / 150 -> EF2 / EF1 = 140 / 150 = 0.9333 -> Drift = 6.67%
        self.assertAlmostEqual(row["drift_pct"], (1.0 - (140.0 / 150.0)) * 100.0, places=1)

        # Stride = (5000 / 30) / 160 = 1.04 m
        self.assertEqual(row["stride_m"], 1.04)

    def test_cadence_with_pause_split(self):
        # 30 min run (10:00 to 10:30) with 2 min pause in H2 (pause_h1=0, pause_h2=120,000 ms)
        st = pd.Timestamp("2026-06-01 10:00:00").value // 10**6
        et = pd.Timestamp("2026-06-01 10:30:00").value // 10**6
        runs = pd.DataFrame([{
            "row_id": 1,
            "app_info_id": 1,
            "start_time": st,
            "end_time": et,
            "exercise_type": 33,
            "title": "Running",
            "distance_meters": 5000.0,
            "pause_ms": 120000,
            "pause_h1_ms": 0,
            "pause_h2_ms": 120000,
        }])

        # Steps: 1500 steps in H1 (15 min active -> 100 spm), 1300 steps in H2 (13 min active -> 100 spm)
        step_records = [
            {"app_info_id": 1, "start_time": st, "end_time": st + 15 * 60 * 1000, "count": 1500},
            {"app_info_id": 1, "start_time": st + 15 * 60 * 1000, "end_time": et, "count": 1300},
        ]
        steps_df = pd.DataFrame(step_records)

        res = calculate_running_metrics(runs, steps_df=steps_df)
        row = res.iloc[0]
        self.assertEqual(row["duration_min"], 28.0)
        self.assertEqual(row["cadence"], 100.0)
        self.assertEqual(row["cadence1"], 100.0)
        self.assertEqual(row["cadence2"], 100.0)

    def test_open_database_file_and_zip(self):
        import sqlite3
        import tempfile
        import zipfile
        from health_connect.db import open_database

        with tempfile.TemporaryDirectory() as td:
            db_file = f"{td}/test.db"
            conn = sqlite3.connect(db_file)
            conn.execute("CREATE TABLE test_table (id INT);")
            conn.commit()
            conn.close()

            # Test direct file open
            with open_database(db_file) as c:
                cur = c.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
                self.assertIn("test_table", [r[0] for r in cur.fetchall()])

            # Test zip archive open
            zip_file = f"{td}/archive.zip"
            with zipfile.ZipFile(zip_file, "w") as zf:
                zf.write(db_file, arcname="exported.db")

            with open_database(zip_file) as c:
                cur = c.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
                self.assertIn("test_table", [r[0] for r in cur.fetchall()])


if __name__ == "__main__":
    unittest.main()
