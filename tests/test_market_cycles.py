import unittest
import pandas as pd
import plotly.graph_objects as go
from market_cycles import market_phase, shade_downturns, annual_activity


class MarketTests(unittest.TestCase):
    def test_known_period_and_unknown_years(self):
        self.assertEqual(market_phase(2022), "하락기")
        self.assertEqual(market_phase(2023), "하락기")
        self.assertEqual(market_phase(2025), "상승기")
        self.assertEqual(market_phase(2026), "미분류")
        self.assertEqual(market_phase(2005), "미분류")

    def test_shading_clips_to_selected_months(self):
        fig = shade_downturns(go.Figure(), "2022-06", "2023-03")
        self.assertEqual(len(fig.layout.shapes), 2)
        self.assertEqual(fig.layout.shapes[0].x0, "2022-07-01T00:00:00")
        self.assertEqual(fig.layout.shapes[1].x1, "2023-04-01T00:00:00")
        self.assertEqual(fig.layout.shapes[0].layer, "below")
        self.assertEqual(len(shade_downturns(go.Figure(), "2024-07", "2026-09").layout.shapes), 0)

    def test_counts_use_filtered_data_and_exclude_unclassified_years(self):
        df = pd.DataFrame({"계약일": ["2022-01-01", "2022-05-01", "2025-12-01", "2026-01-01"]})
        result = annual_activity(df, "2022-01", "2026-09")
        self.assertEqual(result["조회된 거래 건수"].tolist(), [2, 0, 0, 1])
        self.assertEqual(result["서울 시장"].tolist(), ["하락기", "하락기", "상승기", "상승기"])

    def test_phase_mark_and_badge_colors(self):
        from market_cycles import phase_badge_colors, phase_mark

        self.assertEqual(phase_mark("상승기"), "(+)")
        self.assertEqual(phase_mark("하락기"), "(-)")
        self.assertEqual(phase_mark("미분류"), "미분류")
        self.assertEqual(phase_badge_colors("상승기")[0], "#fee2e2")
        self.assertEqual(phase_badge_colors("하락기")[0], "#dbeafe")

class ComparisonTests(unittest.TestCase):
    def test_annualized_counts_include_zero_months(self):
        from market_cycles import phase_comparison
        frame = pd.DataFrame({"계약일": ["2023-07-01", "2023-08-01", "2024-01-01", "2026-01-01"]})
        result = phase_comparison(frame, "2023-07", "2024-12").set_index("시장 국면")
        self.assertEqual(result.loc["상승기", "비교 기간(개월)"], 12)
        self.assertEqual(result.loc["하락기", "비교 기간(개월)"], 6)
        self.assertEqual(result.loc["상승기", "연평균 거래 건수(연환산)"], 2)
        self.assertEqual(result.loc["하락기", "연평균 거래 건수(연환산)"], 2)

    def test_absent_phase_has_no_average(self):
        from market_cycles import phase_comparison
        frame = pd.DataFrame({"계약일": ["2025-01-01"]})
        result = phase_comparison(frame, "2025-01", "2026-12").set_index("시장 국면")
        self.assertEqual(result.loc["상승기", "비교 기간(개월)"], 12)
        self.assertTrue(pd.isna(result.loc["하락기", "연평균 거래 건수(연환산)"]))


class MonthlyIndexTests(unittest.TestCase):
    def test_half_years_can_have_opposite_directions(self):
        from market_cycles import half_phase
        self.assertEqual(half_phase("2022-06-30"), "상승기")
        self.assertEqual(half_phase("2022-07-01"), "하락기")
        self.assertEqual(half_phase("2023-07-01"), "상승기")
        self.assertEqual(half_phase("2024-01-01"), "하락기")
        self.assertEqual(half_phase("2026-01-01"), "미분류")

    def test_source_months_complete(self):
        from market_cycles import _INDEX
        expected = pd.period_range("2005-12", "2025-12", freq="M").astype(str)
        self.assertEqual(set(_INDEX), set(expected))
        self.assertTrue(all(value > 0 for value in _INDEX.values()))
