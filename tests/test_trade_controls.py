import unittest
import pandas as pd
from trade_controls import recent_range, date_bounds, area_values, area_label, as_period_range


class PeriodTests(unittest.TestCase):
    def test_recent_includes_current_month(self):
        self.assertEqual(recent_range(6, "2026-09-11"), ("2026-04", "2026-09"))
        self.assertEqual(recent_range(120, "2026-09-11"), ("2016-10", "2026-09"))
        self.assertEqual(recent_range(3, "2026-01-01"), ("2025-11", "2026-01"))

    def test_select_slider_single_month_still_returns_range(self):
        self.assertEqual(as_period_range("2026-09"), ("2026-09", "2026-09"))
        self.assertEqual(as_period_range(("2026-01", "2026-09")), ("2026-01", "2026-09"))
        self.assertEqual(as_period_range(["2026-09"]), ("2026-09", "2026-09"))
        self.assertEqual(as_period_range(("2026-09", "2026-01")), ("2026-01", "2026-09"))

    def test_today_cutoff_and_leap_month(self):
        self.assertEqual(date_bounds("2026-04", "2026-09", "2026-09-11")[1], pd.Timestamp("2026-09-11"))
        self.assertEqual(date_bounds("2024-01", "2024-02", "2026-09-11")[1], pd.Timestamp("2024-02-29"))

    def test_area_truncates_instead_of_rounding(self):
        frame = pd.DataFrame({"전용면적_num": [59.99, 84.72, 84.99, 114.01, None]})
        self.assertEqual(area_values(frame, True).dropna().tolist(), [59, 84, 84, 114])
        self.assertEqual(area_values(frame, False).dropna().tolist(), [59.99, 84.72, 84.99, 114.01])

    def test_area_label_hides_decimals_when_grouped(self):
        self.assertEqual(area_label(84.72), "84.72㎡")
        self.assertEqual(area_label(84.72, True), "84㎡")
        self.assertEqual(area_label(84.0), "84㎡")
