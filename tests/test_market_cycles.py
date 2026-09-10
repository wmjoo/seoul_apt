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
        self.assertEqual(fig.layout.shapes[0].x0, "2022-06-01T00:00:00")
        self.assertEqual(fig.layout.shapes[1].x1, "2023-04-01T00:00:00")
        self.assertEqual(fig.layout.shapes[0].layer, "below")
        self.assertEqual(len(shade_downturns(go.Figure(), "2024-01", "2026-09").layout.shapes), 0)

    def test_counts_use_filtered_data_and_exclude_unclassified_years(self):
        df = pd.DataFrame({"계약일": ["2022-01-01", "2022-05-01", "2025-12-01", "2026-01-01"]})
        result = annual_activity(df, "2022-01", "2026-09")
        self.assertEqual(result["조회된 거래 건수"].tolist(), [2, 0, 0, 1])
        self.assertEqual(result["서울 시장"].tolist(), ["하락기", "하락기", "상승기", "상승기"])
