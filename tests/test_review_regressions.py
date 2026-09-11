import unittest
from unittest.mock import Mock, patch
import pandas as pd
import auth
import molit_trades as trades
import sheets_store as sheets


class StorageTests(unittest.TestCase):
    def test_read_failure_aborts_collection_before_fetch_or_save(self):
        with patch.object(trades, "has_molit_api_key", return_value=True), \
             patch.object(sheets, "is_sheets_configured", return_value=True), \
             patch.object(sheets, "load_trades", side_effect=RuntimeError("offline")), \
             patch.object(trades, "MolitTradeClient") as client, \
             patch.object(trades, "save_trade_history") as save:
            with self.assertRaises(RuntimeError):
                trades.collect_trades(["동대문구"], "202401", "202401")
            client.return_value.fetch_month.assert_not_called()
            save.assert_not_called()

    def test_failed_write_never_clears_old_rows(self):
        ws = Mock(row_count=100, col_count=8)
        ws.update.side_effect = RuntimeError("offline")
        with patch.object(sheets, "_worksheet", return_value=ws):
            with self.assertRaises(RuntimeError):
                sheets.save_trades(pd.DataFrame({"지번": ["001-2"]}))
        ws.clear.assert_not_called()
        ws.batch_clear.assert_not_called()
        ws.resize.assert_not_called()

    def test_success_writes_literal_values_before_cleanup(self):
        ws = Mock(row_count=100, col_count=8)
        with patch.object(sheets, "_worksheet", return_value=ws):
            sheets.save_trades(pd.DataFrame({"지번": ["001-2", "=literal"]}))
        self.assertEqual(ws.update.call_args.kwargs["value_input_option"], "RAW")
        self.assertEqual(ws.update.call_args.kwargs["values"][1], ["001-2"])
        ws.clear.assert_not_called()
        calls = [call[0] for call in ws.mock_calls]
        self.assertLess(calls.index("update"), calls.index("batch_clear"))

    def test_save_trades_splits_district_sheets_and_keeps_reg_dt_last(self):
        writes = []

        def capture(title, df):
            writes.append((title, list(df.columns), df["구"].tolist()))

        frame = pd.DataFrame({
            "구": ["성북구", "강남구"],
            "지번": ["1", "2"],
            "REG_DT": ["2026-09-11 09:00:00", "2026-09-11 09:01:00"],
        })
        with patch.object(sheets, "_write_df", side_effect=capture):
            sheets.save_trades(frame)
        self.assertEqual(set(title for title, _, _ in writes), {"성북구", "강남구"})
        for _, cols, _ in writes:
            self.assertEqual(cols[-1], "REG_DT")

    def test_districts_sheet_keeps_collection_metadata(self):
        existing = pd.DataFrame({
            "구": ["성북구"],
            "LAST_REG_DT": ["2026-09-10 08:00:00"],
            "최초 거래일": ["2016-01-05"],
            "최종 거래일": ["2026-09-09"],
        })
        written = []
        with patch.object(sheets, "load_district_meta", return_value=existing), \
             patch.object(sheets, "save_district_meta", side_effect=written.append):
            sheets.save_districts(["성북구", "강남구"])
            sheets.update_district_meta(
                {"성북구": {"LAST_REG_DT": "2026-09-11 09:00:00", "최종 거래일": "2026-09-11"}},
                order=["성북구", "강남구"],
            )
        saved = written[-1]
        seongbuk = saved.loc[saved["구"] == "성북구"].iloc[0]
        self.assertEqual(list(saved.columns), sheets.DISTRICT_META_COLS)
        self.assertEqual(seongbuk["LAST_REG_DT"], "2026-09-11 09:00:00")
        self.assertEqual(seongbuk["최초 거래일"], "2016-01-05")
        self.assertEqual(seongbuk["최종 거래일"], "2026-09-11")
        self.assertIn("강남구", set(saved["구"]))
        self.assertEqual(sheets.last_reg_date("성북구", existing), pd.Timestamp("2026-09-10").date())

    def test_load_trades_reads_only_requested_district_sheets(self):
        reads = []

        def fake_read(title):
            reads.append(title)
            return pd.DataFrame({"구": [title], "계약일": ["2026-01-01"], "아파트명": ["A"]})

        with patch.object(sheets, "_read_existing_df", side_effect=fake_read), \
             patch.object(sheets, "_district_sheet_names", return_value=["성북구", "강남구", "송파구"]):
            out = sheets.load_trades(districts=["성북구"])
        self.assertEqual(reads, ["성북구"])
        self.assertEqual(out["구"].tolist(), ["성북구"])
        reads.clear()
        with patch.object(sheets, "_read_existing_df", side_effect=fake_read), \
             patch.object(sheets, "_district_sheet_names", return_value=["성북구", "강남구"]):
            sheets.load_trades()
        self.assertEqual(reads, ["성북구", "강남구"])

    def test_permission_error_does_not_create_worksheet(self):
        book = Mock()
        book.worksheet.side_effect = PermissionError()
        with patch.object(sheets, "_spreadsheet", return_value=book):
            with self.assertRaises(PermissionError):
                sheets._worksheet("trades")
        book.add_worksheet.assert_not_called()

    def test_missing_worksheet_can_be_created(self):
        from gspread.exceptions import WorksheetNotFound
        book = Mock()
        book.worksheet.side_effect = WorksheetNotFound()
        with patch.object(sheets, "_spreadsheet", return_value=book):
            sheets._worksheet("trades")
        book.add_worksheet.assert_called_once()

    def test_no_sleep_after_last_retry(self):
        action = Mock(side_effect=RuntimeError("429"))
        with patch.object(sheets.time, "sleep") as sleep:
            with self.assertRaises(RuntimeError):
                sheets._with_sheets_retry(action, retries=2)
        self.assertEqual(action.call_count, 2)
        sleep.assert_called_once_with(10)


class AuthTests(unittest.TestCase):
    def test_korean_password(self):
        with patch.object(auth, "get_tracker_users", return_value={"tester": "한글암호!"}), \
             patch.object(auth.st, "session_state", {}):
            self.assertTrue(auth.login_tracker("tester", "한글암호!"))
            self.assertFalse(auth.login_tracker("tester", "다른암호"))
