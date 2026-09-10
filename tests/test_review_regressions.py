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
