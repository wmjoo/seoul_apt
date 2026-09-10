import unittest
from unittest.mock import patch, Mock
import pandas as pd
import molit_trades as m
from trade_metadata import complex_metadata


class CollectionTests(unittest.TestCase):
    def test_completion_requires_closed_month(self):
        log = pd.DataFrame([
            {"구": "성북구", "연월": "202401", "수집시각": "2024-01-31T23:59:00"},
            {"구": "성북구", "연월": "202402", "수집시각": "2024-03-01T00:00:00"},
        ])
        self.assertEqual(m.completed_months(log), {("성북구", "202402")})

    def test_replace_preserves_equal_real_trades_and_other_months(self):
        old = pd.DataFrame([
            {"구": "성북구", "계약일": "2024-01-02", "아파트명": "A"},
            {"구": "성북구", "계약일": "2024-02-02", "아파트명": "A"},
        ])
        row = {"구": "성북구", "계약일": "2024-01-03", "아파트명": "A"}
        result = m.replace_collected_months(old, [row, row], {("성북구", "202401")})
        self.assertEqual(len(result), 3)
        self.assertEqual((result["계약일"] == "2024-01-03").sum(), 2)
        result = m.replace_collected_months(old, [], {("성북구", "202401")})
        self.assertEqual(list(result["계약일"]), ["2024-02-02"])

    def test_failed_save_never_marks_completion(self):
        with patch.object(m, "has_molit_api_key", return_value=True), \
             patch.object(m, "load_trade_history", return_value=pd.DataFrame()), \
             patch.object(m, "load_collection_log", return_value=pd.DataFrame()), \
             patch.object(m, "MolitTradeClient") as client, \
             patch.object(m.time, "sleep"), \
             patch.object(m, "save_trade_history", side_effect=RuntimeError("failed")), \
             patch.object(m, "save_collection_log") as log:
            client.return_value.fetch_month.return_value = []
            with self.assertRaises(RuntimeError):
                m.collect_trades(["성북구"], "202401", "202401")
            log.assert_not_called()

    def test_zero_trade_month_is_recorded_and_force_refetches(self):
        completed = pd.DataFrame([{"구": "성북구", "연월": "202401",
                                    "수집시각": "2024-02-02", "건수": 0}])
        for skip in [True, False]:
            with patch.object(m, "has_molit_api_key", return_value=True), \
                 patch.object(m, "load_trade_history", return_value=pd.DataFrame()), \
                 patch.object(m, "load_collection_log", return_value=completed), \
                 patch.object(m, "MolitTradeClient") as client, \
                 patch.object(m.time, "sleep"), \
                 patch.object(m, "save_trade_history"), \
                 patch.object(m, "save_collection_log") as log:
                client.return_value.fetch_month.return_value = []
                m.collect_trades(["성북구"], "202401", "202401", skip_complete_months=skip)
                self.assertEqual(client.return_value.fetch_month.call_count, 0 if skip else 1)
                self.assertEqual(log.call_count, 0 if skip else 1)

    def test_metadata_alias_and_missing_columns(self):
        trades = pd.DataFrame([{"아파트명": "종암에스케이", "구": "성북구",
                                "법정동": "종암동", "지번": "1", "도로명": None}] * 2)
        apartments = pd.DataFrame([{"아파트명": "종암SK아파트", "자치구": "성북구",
                                    "동": "종암동", "세대수": 100, "난방방식": None}])
        result = complex_metadata(trades, apartments)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["세대수"], 100)
        self.assertNotIn("도로명", result)
        self.assertNotIn("난방방식", result)
