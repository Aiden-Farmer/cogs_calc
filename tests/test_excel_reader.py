from __future__ import annotations

import os
import stat
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import openpyxl
import pytest

from src.data.datarows import Header, InventoryRow
from src.data.excel.reader import (
    _XL_CALCULATION_AUTOMATIC,
    _XL_CALCULATION_MANUAL,
    CouldNotOpenFile,
    ExcelDataSource,
    ExcelFileReader,
    UnsupportedPlatformError,
    _backup_path,
    _clear_readonly,
    _prune_sheet,
    _require_windows,
    remove_wb_dates_after_target,
)
from src.data.reader import AbstractReader

_INV_HEADER = Header.inventory_row(sku=0, base_sku=1, inventory=2)
_OLE_FILE_SIG = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _write_workbook(tmp_path, rows, title="Sheet") -> str:
    wb = openpyxl.Workbook()
    wb.active.title = title
    for row in rows:
        wb.active.append(row)
    path = tmp_path / "book.xlsx"
    wb.save(path)
    return str(path)


class TestInitializeData:
    def test_raises_typeerror_for_chartsheet(self, tmp_path):
        path = _write_workbook(tmp_path, [["header"]], title="Chart1")
        chart_wb = MagicMock()
        chart_wb.__getitem__.return_value = object()  # not a ReadOnlyWorksheet

        with patch("src.data.excel.reader.xl.load_workbook", return_value=chart_wb):
            with pytest.raises(TypeError):
                ExcelFileReader(
                    ExcelDataSource(path, "Chart1"), _INV_HEADER, InventoryRow
                )

    def test_password_protected_file_is_decrypted_and_opened(self, tmp_path):
        encrypted_path = tmp_path / "protected.xlsx"
        encrypted_path.write_bytes(_OLE_FILE_SIG + b"\x00" * 8)

        real_wb = openpyxl.load_workbook(
            _write_workbook(tmp_path, [["header"]]), read_only=True, data_only=True
        )
        mock_office_file = MagicMock()

        with (
            patch("src.data.excel.reader.xl.load_workbook", return_value=real_wb),
            patch("src.data.excel.reader.getpass", return_value="secret"),
            patch(
                "src.data.excel.reader.msoffcrypto.OfficeFile",
                return_value=mock_office_file,
            ),
        ):
            reader = ExcelFileReader(
                ExcelDataSource(str(encrypted_path), "Sheet"), _INV_HEADER, InventoryRow
            )

        mock_office_file.load_key.assert_called_once_with(password="secret")
        mock_office_file.decrypt.assert_called_once()
        assert reader.wb is real_wb

    def test_raises_couldnotopenfile_when_decryption_fails(self, tmp_path):
        encrypted_path = tmp_path / "protected.xlsx"
        encrypted_path.write_bytes(_OLE_FILE_SIG + b"\x00" * 8)

        with (
            patch.object(
                ExcelFileReader, "_handle_password_protected_xl", return_value=None
            ),
            pytest.raises(CouldNotOpenFile),
        ):
            ExcelFileReader(
                ExcelDataSource(str(encrypted_path), "Sheet"),
                _INV_HEADER,
                InventoryRow,
            )

    def test_raises_valueerror_when_initialize_data_returns_falsy(self):
        with (
            patch.object(
                ExcelFileReader, "_initialize_data", return_value=(None, None)
            ),
            pytest.raises(ValueError),
        ):
            ExcelFileReader(
                ExcelDataSource("book.xlsx", "Sheet"), _INV_HEADER, InventoryRow
            )


class TestExcelFileReaderMisc:
    def test_close_closes_workbook(self, tmp_path):
        path = _write_workbook(tmp_path, [["header"]])
        reader = ExcelFileReader(
            ExcelDataSource(path, "Sheet"), _INV_HEADER, InventoryRow
        )

        with patch.object(reader.wb, "close") as mock_close:
            reader.close()

        mock_close.assert_called_once()

    def test_iter_raw_skips_header_row(self, tmp_path):
        path = _write_workbook(tmp_path, [["header"], ["a", "a", 1], ["b", "b", 2]])
        reader = ExcelFileReader(
            ExcelDataSource(path, "Sheet"), _INV_HEADER, InventoryRow
        )

        rows = list(reader._iter_raw())

        assert rows == [("a", "a", 1), ("b", "b", 2)]

    def test_readline_parses_rows_into_return_type(self, tmp_path):
        path = _write_workbook(
            tmp_path, [["header"], ["a", "a", 1], ["bad-sku", "mismatch", 2]]
        )
        reader = ExcelFileReader(
            ExcelDataSource(path, "Sheet"), _INV_HEADER, InventoryRow
        )

        # Bypass the @split_kits decorator (it depends on process-wide kit data
        # loaded from disk at import time) to exercise the base read pipeline directly.
        rows = list(AbstractReader.readline(reader))

        assert len(rows) == 1
        assert rows[0].sku == "a"


class TestRequireWindows:
    def test_raises_on_non_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")

        with pytest.raises(UnsupportedPlatformError):
            _require_windows("some feature")

    def test_no_op_on_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")

        _require_windows("some feature")  # should not raise


class TestBackupPath:
    def test_backup_path_preserves_dir_and_suffix_and_is_unique_looking(self, tmp_path):
        original = tmp_path / "inventory.xlsx"

        backup = _backup_path(str(original))

        assert backup.parent == original.parent
        assert backup.suffix == ".xlsx"
        assert backup.name.startswith("inventory_backup_")
        assert backup != original


class TestClearReadonly:
    def test_clears_readonly_attribute_when_set(self, tmp_path):
        path = tmp_path / "inventory.xlsx"
        path.write_bytes(b"pretend workbook bytes")
        os.chmod(path, stat.S_IREAD)

        _clear_readonly(str(path))

        assert os.stat(path).st_mode & stat.S_IWRITE

    def test_leaves_a_writable_file_untouched(self, tmp_path):
        path = tmp_path / "inventory.xlsx"
        path.write_bytes(b"pretend workbook bytes")
        mode_before = os.stat(path).st_mode

        _clear_readonly(str(path))

        assert os.stat(path).st_mode == mode_before


class TestPruneSheet:
    def _make_sheet(self, rows: list[tuple]):
        """rows holds one tuple per data row (2, 3, ...), each holding
        every column's value for that row (all columns, not just the date
        column). Pass [] for a header-only sheet with no data rows."""
        sheet = MagicMock()
        sheet.Name = "Sheet"
        col_count = len(rows[0]) if rows else 1
        last_row = 1 + len(rows)
        sheet.UsedRange.Row = 1
        sheet.UsedRange.Column = 1
        sheet.UsedRange.Rows.Count = last_row
        sheet.UsedRange.Columns.Count = col_count
        sheet.Cells.side_effect = lambda row, col: SimpleNamespace(row=row, col=col)

        # Mirrors the real COM quirk: a true 1x1 range's .Value is a bare
        # scalar, not a 1x1 tuple-of-tuples. A single row with >1 column,
        # or >1 row with a single column, is already correctly nested.
        read_value = rows[0][0] if len(rows) == 1 and col_count == 1 else tuple(rows)
        read_range = SimpleNamespace(Value=read_value)

        write_range = MagicMock()
        # First Range() call is the bulk read; a second (only made when
        # there's something to keep) is the bulk write-back.
        range_calls = [read_range, write_range]
        sheet.Range.side_effect = lambda *a: (
            range_calls.pop(0) if range_calls else write_range
        )
        sheet.write_range = write_range

        deleted_address: list[str] = []

        def _rows(address: str):
            row_range = MagicMock()
            row_range.Delete.side_effect = lambda: deleted_address.append(address)
            return row_range

        sheet.Rows.side_effect = _rows
        sheet.deleted_address = deleted_address
        return sheet

    def test_rewrites_kept_rows_and_deletes_the_stale_tail(self):
        target = datetime(2024, 1, 1)
        rows = [
            ("sku-a", 10, datetime(2023, 6, 1)),  # row 2: kept
            ("sku-b", 20, None),  # row 3: blank date -> dropped
            ("sku-c", 30, datetime(2024, 6, 1)),  # row 4: after target -> dropped
            ("sku-d", 40, datetime(2024, 1, 1)),  # row 5: equal to target -> kept
        ]
        sheet = self._make_sheet(rows)

        _prune_sheet(sheet, date_col=2, target=target)

        assert sheet.write_range.Value == (
            ("sku-a", 10, datetime(2023, 6, 1)),
            ("sku-d", 40, datetime(2024, 1, 1)),
        )
        assert sheet.deleted_address == ["4:5"]

    def test_rows_need_not_be_sorted_by_date(self):
        # Stale rows scattered among kept rows still end up correctly
        # partitioned -- kept rows preserve their relative order.
        rows = [
            ("sku-a", 1, datetime(2024, 6, 1)),  # stale
            ("sku-b", 2, datetime(2023, 1, 1)),  # kept
            ("sku-c", 3, datetime(2024, 7, 1)),  # stale
            ("sku-d", 4, datetime(2023, 2, 1)),  # kept
        ]
        sheet = self._make_sheet(rows)

        _prune_sheet(sheet, date_col=2, target=datetime(2024, 1, 1))

        assert sheet.write_range.Value == (
            ("sku-b", 2, datetime(2023, 1, 1)),
            ("sku-d", 4, datetime(2023, 2, 1)),
        )
        assert sheet.deleted_address == ["4:5"]

    def test_all_rows_removed_skips_write_and_deletes_the_whole_range(self):
        rows = [
            ("sku-a", 1, datetime(2024, 6, 1)),
            ("sku-b", 2, None),
        ]
        sheet = self._make_sheet(rows)

        _prune_sheet(sheet, date_col=2, target=datetime(2024, 1, 1))

        assert sheet.deleted_address == ["2:3"]
        assert sheet.Range.call_count == 1  # read only, no write-back call

    def test_nothing_to_remove_skips_write_and_delete(self):
        rows = [("sku-a", 1, datetime(2023, 1, 1))]
        sheet = self._make_sheet(rows)

        _prune_sheet(sheet, date_col=2, target=datetime(2024, 1, 1))

        sheet.Rows.assert_not_called()
        assert sheet.Range.call_count == 1

    def test_skips_header_only_sheet_with_no_data_rows(self):
        sheet = self._make_sheet([])

        _prune_sheet(sheet, date_col=0, target=datetime(2024, 1, 1))

        sheet.Range.assert_not_called()
        sheet.Rows.assert_not_called()

    def test_handles_tz_aware_cell_values_against_a_naive_target(self):
        # Real Excel COM automation has been observed returning tz-aware
        # datetimes for date cells, despite target sometimes being naive --
        # must not raise "can't compare offset-naive and offset-aware".
        rows = [
            ("sku-a", 1, datetime(2023, 6, 1, tzinfo=UTC)),  # kept
            ("sku-b", 2, datetime(2024, 6, 1, tzinfo=UTC)),  # dropped
        ]
        sheet = self._make_sheet(rows)

        _prune_sheet(sheet, date_col=2, target=datetime(2024, 1, 1))

        assert sheet.deleted_address == ["3:3"]

    def test_handles_naive_cell_values_against_a_tz_aware_target(self):
        rows = [
            ("sku-a", 1, datetime(2023, 6, 1)),  # kept
            ("sku-b", 2, datetime(2024, 6, 1)),  # dropped
        ]
        sheet = self._make_sheet(rows)

        _prune_sheet(sheet, date_col=2, target=datetime(2024, 1, 1, tzinfo=UTC))

        assert sheet.deleted_address == ["3:3"]

    def test_converts_0_indexed_date_col_to_the_correct_column_in_each_row(self):
        # date_col=4 is the 5th (last) column in each row tuple; a stale
        # date there -- not a coincidentally-stale value elsewhere in the
        # row -- must be what drives the keep/drop decision.
        rows = [("sku-a", "b", "c", "d", datetime(2024, 6, 1))]
        sheet = self._make_sheet(rows)

        _prune_sheet(sheet, date_col=4, target=datetime(2024, 1, 1))

        assert sheet.deleted_address == ["2:2"]

    def test_true_1x1_range_collapses_on_both_read_and_write(self):
        rows = [
            (datetime(2023, 1, 1),),  # single column, kept
            (datetime(2024, 6, 1),),  # single column, dropped
        ]
        sheet = self._make_sheet(rows)

        _prune_sheet(sheet, date_col=0, target=datetime(2024, 1, 1))

        assert sheet.write_range.Value == datetime(2023, 1, 1)
        assert sheet.deleted_address == ["3:3"]

    def _make_chunked_sheet(
        self, used_row_count: int, used_col_count: int, range_results: list
    ):
        """Lower-level than _make_sheet: for tests exercising more than one
        read/write cycle. range_results is consumed in call order by
        sheet.Range() -- each entry is either a SimpleNamespace(Value=...)
        for a read, or a bare MagicMock() placeholder for a write (its
        .Value attribute records what got written, for the test to
        inspect afterward)."""
        sheet = MagicMock()
        sheet.Name = "Sheet"
        sheet.UsedRange.Row = 1
        sheet.UsedRange.Column = 1
        sheet.UsedRange.Rows.Count = used_row_count + 1
        sheet.UsedRange.Columns.Count = used_col_count
        sheet.Cells.side_effect = lambda row, col: SimpleNamespace(row=row, col=col)

        queue = list(range_results)
        sheet.Range.side_effect = lambda *a: queue.pop(0)

        deleted_address: list[str] = []

        def _rows(address: str):
            row_range = MagicMock()
            row_range.Delete.side_effect = lambda: deleted_address.append(address)
            return row_range

        sheet.Rows.side_effect = _rows
        sheet.deleted_address = deleted_address
        return sheet

    def test_processes_rows_in_chunks_and_carries_the_write_cursor_across_them(self):
        # 5 data rows (single column: just the date), chunk size patched to
        # 2 -> chunks are rows [2:3], [4:5], [6:6].
        target = datetime(2024, 1, 1)
        v2, v3 = datetime(2023, 1, 1), datetime(2024, 6, 1)  # kept, stale
        v4, v5 = datetime(2023, 2, 1), datetime(2023, 3, 1)  # kept, kept
        v6 = datetime(2024, 7, 1)  # stale

        chunk1_read = SimpleNamespace(Value=((v2,), (v3,)))
        chunk1_write = MagicMock()  # rows 2:2 -- kept only v2, true 1x1
        chunk2_read = SimpleNamespace(Value=((v4,), (v5,)))
        chunk2_write = MagicMock()  # rows 3:4 -- write cursor now trails read
        chunk3_read = SimpleNamespace(Value=v6)  # rows 6:6 -- true 1x1 read
        # no chunk3 write: v6 is stale, nothing kept in that chunk

        sheet = self._make_chunked_sheet(
            used_row_count=5,
            used_col_count=1,
            range_results=[
                chunk1_read,
                chunk1_write,
                chunk2_read,
                chunk2_write,
                chunk3_read,
            ],
        )

        with patch("src.data.excel.reader._CHUNK_ROWS", 2):
            _prune_sheet(sheet, date_col=0, target=target)

        assert chunk1_write.Value == v2
        assert chunk2_write.Value == ((v4,), (v5,))
        assert sheet.deleted_address == ["5:6"]


class TestRemoveWbDatesAfterTarget:
    def _fake_win32_module(self, mock_app):
        fake_module = MagicMock()
        fake_module.Dispatch.return_value = mock_app
        return fake_module

    def test_raises_on_non_windows_before_touching_win32com(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(sys, "platform", "linux")

        with pytest.raises(UnsupportedPlatformError):
            remove_wb_dates_after_target(
                str(tmp_path / "inventory.xlsx"), datetime(2024, 1, 1), {}
            )

    def test_backs_up_prunes_recalculates_and_saves_on_success(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(sys, "platform", "win32")
        src_path = tmp_path / "inventory.xlsx"
        src_path.write_bytes(b"pretend workbook bytes")

        mock_app = MagicMock()
        mock_wb = mock_app.Workbooks.Open.return_value
        mock_wb.ReadOnly = False
        mock_sheet = mock_wb.Sheets.return_value
        mock_sheet.UsedRange.Row = 1
        mock_sheet.UsedRange.Rows.Count = 1  # header only, nothing to prune
        monkeypatch.setitem(
            sys.modules, "win32com.client", self._fake_win32_module(mock_app)
        )

        remove_wb_dates_after_target(
            str(src_path), datetime(2024, 1, 1), {"Transactions": 0}
        )

        backups = list(tmp_path.glob("inventory_backup_*.xlsx"))
        assert len(backups) == 1
        assert backups[0].read_bytes() == src_path.read_bytes()

        mock_wb.Sheets.assert_called_once_with("Transactions")
        mock_app.CalculateFullRebuild.assert_called_once()
        mock_wb.Save.assert_called_once()
        mock_wb.Close.assert_called_once_with(SaveChanges=False)
        mock_app.Quit.assert_called_once()
        assert mock_app.ScreenUpdating is False
        # Restored to automatic before Save() so the saved file doesn't
        # persist manual calculation mode.
        assert mock_app.Calculation == _XL_CALCULATION_AUTOMATIC

    def test_calculation_is_manual_while_pruning(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        src_path = tmp_path / "inventory.xlsx"
        src_path.write_bytes(b"pretend workbook bytes")

        mock_app = MagicMock()
        mock_app.Workbooks.Open.return_value.ReadOnly = False
        monkeypatch.setitem(
            sys.modules, "win32com.client", self._fake_win32_module(mock_app)
        )

        seen_calculation = []

        def _capture_prune(sheet, date_col, target):
            seen_calculation.append(mock_app.Calculation)

        with patch(
            "src.data.excel.reader._prune_sheet", side_effect=_capture_prune
        ):
            remove_wb_dates_after_target(
                str(src_path), datetime(2024, 1, 1), {"Transactions": 0}
            )

        assert seen_calculation == [_XL_CALCULATION_MANUAL]

    def test_raises_and_still_quits_when_opened_readonly_anyway(
        self, tmp_path, monkeypatch
    ):
        # A workbook can have its own "Always Open Read-Only" property,
        # independent of the OS file attribute -- even with ReadOnly=False
        # and IgnoreReadOnlyRecommended=True passed to Workbooks.Open,
        # confirm we fail fast with a clear error rather than proceeding
        # through a full prune only to fail at Save().
        monkeypatch.setattr(sys, "platform", "win32")
        src_path = tmp_path / "inventory.xlsx"
        src_path.write_bytes(b"pretend workbook bytes")

        mock_app = MagicMock()
        mock_wb = mock_app.Workbooks.Open.return_value
        mock_wb.ReadOnly = True
        monkeypatch.setitem(
            sys.modules, "win32com.client", self._fake_win32_module(mock_app)
        )

        with pytest.raises(RuntimeError, match="read-only"):
            remove_wb_dates_after_target(
                str(src_path), datetime(2024, 1, 1), {"Transactions": 0}
            )

        mock_wb.Sheets.assert_not_called()
        mock_wb.Save.assert_not_called()
        mock_wb.Close.assert_called_once_with(SaveChanges=False)
        mock_app.Quit.assert_called_once()

    def test_discards_edits_and_still_quits_on_failure(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        src_path = tmp_path / "inventory.xlsx"
        src_path.write_bytes(b"pretend workbook bytes")

        mock_app = MagicMock()
        mock_wb = mock_app.Workbooks.Open.return_value
        mock_wb.ReadOnly = False
        mock_wb.Sheets.side_effect = RuntimeError("boom")
        monkeypatch.setitem(
            sys.modules, "win32com.client", self._fake_win32_module(mock_app)
        )

        with pytest.raises(RuntimeError):
            remove_wb_dates_after_target(
                str(src_path), datetime(2024, 1, 1), {"Transactions": 0}
            )

        mock_wb.Save.assert_not_called()
        mock_wb.Close.assert_called_once_with(SaveChanges=False)
        mock_app.Quit.assert_called_once()
