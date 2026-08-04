from __future__ import annotations

from unittest.mock import MagicMock, patch

import openpyxl
import pytest

from src.data.datarows import Header, InventoryRow
from src.data.excel.reader import CouldNotOpenFile, ExcelDataSource, ExcelFileReader
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

        with patch.object(
            ExcelFileReader, "_handle_password_protected_xl", return_value=None
        ):
            with pytest.raises(CouldNotOpenFile):
                ExcelFileReader(
                    ExcelDataSource(str(encrypted_path), "Sheet"),
                    _INV_HEADER,
                    InventoryRow,
                )

    def test_raises_valueerror_when_initialize_data_returns_falsy(self):
        with patch.object(
            ExcelFileReader, "_initialize_data", return_value=(None, None)
        ):
            with pytest.raises(ValueError):
                ExcelFileReader(
                    ExcelDataSource("book.xlsx", "Sheet"), _INV_HEADER, InventoryRow
                )


class TestExcelFileReaderMisc:
    def test_close_closes_workbook(self, tmp_path):
        path = _write_workbook(tmp_path, [["header"]])
        reader = ExcelFileReader(ExcelDataSource(path, "Sheet"), _INV_HEADER, InventoryRow)

        with patch.object(reader.wb, "close") as mock_close:
            reader.close()

        mock_close.assert_called_once()

    def test_iter_raw_skips_header_row(self, tmp_path):
        path = _write_workbook(
            tmp_path, [["header"], ["a", "a", 1], ["b", "b", 2]]
        )
        reader = ExcelFileReader(ExcelDataSource(path, "Sheet"), _INV_HEADER, InventoryRow)

        rows = list(reader._iter_raw())

        assert rows == [("a", "a", 1), ("b", "b", 2)]

    def test_readline_parses_rows_into_return_type(self, tmp_path):
        path = _write_workbook(
            tmp_path, [["header"], ["a", "a", 1], ["bad-sku", "mismatch", 2]]
        )
        reader = ExcelFileReader(ExcelDataSource(path, "Sheet"), _INV_HEADER, InventoryRow)

        # Bypass the @split_kits decorator (it depends on process-wide kit data
        # loaded from disk at import time) to exercise the base read pipeline directly.
        rows = list(AbstractReader.readline(reader))

        assert len(rows) == 1
        assert rows[0].sku == "a"
