from __future__ import annotations

import io
import logging
import os
import shutil
import stat
import sys
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from getpass import getpass
from pathlib import Path
from typing import TypeVar
from warnings import filterwarnings
from zipfile import BadZipFile

import msoffcrypto
import openpyxl as xl
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet._read_only import ReadOnlyWorksheet
from tqdm import tqdm

from ..datarow_mutation_utils import split_kits
from ..datarows import RowLike
from ..reader import AbstractReader, FailedRow, Header

logger = logging.getLogger("COGS")

T = TypeVar("T", bound="RowLike")

filterwarnings("ignore", category=UserWarning, module="openpyxl")

_OLE_FILE_SIG = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


@dataclass
class ExcelDataSource:
    wb_path: str
    ws_name: str


class ExcelFileReader(AbstractReader[T, ExcelDataSource]):
    def __init__(
        self, data_source: ExcelDataSource, header: Header, return_type: type[T]
    ):
        self.wb, self.data_source = self._initialize_data(data_source)
        self.rt = return_type
        self.header: Header = header

        if not self.wb or not self.data_source:
            raise ValueError

    @split_kits
    def readline(self) -> Iterator[T | FailedRow]:
        return super().readline()

    def _iter_raw(self) -> Iterable[tuple]:
        for i, raw in enumerate(self.data_source.iter_rows(values_only=True)):
            if i == 0:
                continue
            yield raw

    def _initialize_data(
        self, ds: ExcelDataSource
    ) -> tuple[Workbook, ReadOnlyWorksheet]:
        with open(ds.wb_path, "rb") as f:
            header = f.read(8)

        if header == _OLE_FILE_SIG:
            io_stream = self._handle_password_protected_xl(ds.wb_path)
            if not io_stream:
                raise CouldNotOpenFile(
                    f"{ds.wb_path} is either not a valid xlsx or could not be decrypted",
                )
            wb = xl.load_workbook(
                filename=io_stream,
                read_only=True,
                data_only=True,
            )
        else:
            wb = xl.load_workbook(
                filename=ds.wb_path,
                read_only=True,
                data_only=True,
            )

        ws = wb[ds.ws_name]
        if not isinstance(ws, ReadOnlyWorksheet):
            raise TypeError("Data must be in a Worksheet, not ChartSheet.")
        return wb, ws

    def close(self) -> None:
        """Free wb."""
        self.wb.close()

    @staticmethod
    def _handle_password_protected_xl(filename) -> io.BytesIO | None:
        decrypted = io.BytesIO()
        try:
            with open(filename, "rb") as f:
                # Check for OLE File Hexadecimal signature.
                header = f.read(8)
                if header != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                    return None

                u_input_pass = getpass(
                    f"{filename} is password protected, please enter password: ",
                )
                file = msoffcrypto.OfficeFile(f)
                file.load_key(password=u_input_pass)
                file.decrypt(decrypted)
                return decrypted
        except BadZipFile:
            return None


class UnsupportedPlatformError(OSError):
    pass


def _require_windows(feature: str) -> None:
    """Raise clearly instead of letting a win32-only call fail lower down."""
    if sys.platform != "win32":
        raise UnsupportedPlatformError(
            f"{feature} requires Windows (uses Excel COM automation via pywin32)."
        )


# Maps sheet name -> 0-indexed column holding that row's date. Identifies
# which sheets in a workbook are "transaction" sheets for
# remove_wb_dates_after_target, and where to find the date on each.
type TransactionSheetDateColumns = dict[str, int]

# Late-bound win32com.client.Dispatch has no .constants module, so these
# are hardcoded from the xlCalculation enum.
_XL_CALCULATION_MANUAL = -4135
_XL_CALCULATION_AUTOMATIC = -4105


def remove_wb_dates_after_target(
    wb_path: str,
    target: datetime,
    transaction_sheets: TransactionSheetDateColumns,
) -> None:
    """
    Delete rows missing a date, or dated after `target`, from each sheet
    named in `transaction_sheets`, then recalculate and save.

    Uses Excel COM automation (pywin32) rather than openpyxl: openpyxl has
    no formula engine, so it can't recalculate formulas that reference the
    deleted rows. The original file is backed up before anything is
    changed; on any failure the in-memory edits are discarded and the
    original file on disk is left untouched.
    """
    _require_windows("Removing out-of-range transaction rows")

    import win32com.client as win32

    shutil.copy2(wb_path, _backup_path(wb_path))
    _clear_readonly(wb_path)

    excel = win32.Dispatch("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    wb = None
    try:
        t_open = time.perf_counter()
        wb = excel.Workbooks.Open(
            str(Path(wb_path).resolve()),
            ReadOnly=False,
            # The workbook may have its own "Always Open Read-Only"
            # property set (independent of the OS file attribute cleared
            # above). This *should* make Excel ignore that recommendation,
            # but has been observed not to reliably override it -- hence
            # the wb.ReadOnly check below rather than trusting this alone.
            IgnoreReadOnlyRecommended=True,
        )
        logger.debug(f"[timing] Workbooks.Open: {time.perf_counter() - t_open:.2f}s")

        if wb.ReadOnly:
            raise RuntimeError(
                f"{wb_path} opened as read-only despite ReadOnly=False and "
                "IgnoreReadOnlyRecommended=True. This has been observed "
                "when the workbook itself has 'Always Open Read-Only' set "
                "(File > Info > Protect Workbook), which Excel can honor "
                "regardless of those parameters. Fix: open the file in "
                "Excel, uncheck that option (or File > Save As over "
                "itself), then re-run."
            )

        # Automatic calculation would otherwise recalc dependent formulas on
        # every single row delete below; defer it to the one explicit
        # CalculateFullRebuild() call once all sheets are pruned.
        excel.ScreenUpdating = False
        excel.Calculation = _XL_CALCULATION_MANUAL
        t_prune = time.perf_counter()
        for sheet_name, date_col in tqdm(
            transaction_sheets.items(), desc="Calculating..."
        ):
            _prune_sheet(wb.Sheets(sheet_name), date_col, target)
        logger.debug(
            f"Transactions after --as-of-date removed: {time.perf_counter() - t_prune:.2f}s"
        )

        excel.Calculation = _XL_CALCULATION_AUTOMATIC  # restored before Save();
        # xlsx persists calc mode, would otherwise leave the file in manual mode.
        t_calc = time.perf_counter()
        excel.CalculateFullRebuild()
        logger.info(f"Recalculating inventory: {time.perf_counter() - t_calc:.2f}s")

        t_save = time.perf_counter()
        wb.Save()
        logger.debug(f"save: {time.perf_counter() - t_save:.2f}s")
    finally:
        if wb is not None:
            wb.Close(SaveChanges=False)
        excel.Quit()


def _backup_path(wb_path: str) -> Path:
    src = Path(wb_path)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return src.with_name(f"{src.stem}_backup_{stamp}{src.suffix}")


def _clear_readonly(wb_path: str) -> None:
    """Excel refuses to Save() a workbook whose file has the OS read-only
    attribute set (distinct from being locked open elsewhere), raising
    "We can't save '...' because the file is read-only." This function's
    whole purpose is to edit and save wb_path in place -- and it's already
    backed up before this runs -- so clear the attribute if set rather
    than fail partway through a prune."""
    mode = os.stat(wb_path).st_mode
    if not mode & stat.S_IWRITE:
        os.chmod(wb_path, mode | stat.S_IWRITE)


# Above roughly this many rows per Range.Value get/set, wide sheets (many
# columns, e.g. e-commerce channel exports) have been observed to fail
# with "Not enough memory resources are available to complete this
# operation" -- marshaling the whole 2D array across the COM boundary in
# one call. Chunking keeps each read/write comfortably under that ceiling.
_CHUNK_ROWS = 2000


def _prune_sheet(sheet, date_col: int, target: datetime) -> None:
    """Rewrite the sheet to keep only data rows (below header row 1) whose
    date_col cell holds a date on or before target, dropping rows with a
    blank date.

    Excel COM's per-call cost here is dominated by cross-sheet
    formula-reference bookkeeping triggered on every *structural* edit --
    observed in practice as a single Delete() call costing roughly the
    same whether it covers a dozen rows or a hundred, i.e. a largely
    per-call, not per-row, cost. Deleting matched rows in place therefore
    scales with how many separate calls that takes, which depends on how
    scattered they are -- and dates on these sheets aren't guaranteed
    sorted. So instead: read the used range in _CHUNK_ROWS-sized slices,
    filter to the kept rows in Python, bulk-write each chunk's kept rows
    back starting wherever the last chunk's write left off (a pure value
    overwrite, not a structural edit, so it doesn't pay that per-call
    cost) -- the write cursor never runs ahead of the read position, since
    rows are only ever removed, never added, so this is safe to do
    chunk-by-chunk without buffering the whole sheet in memory -- then
    delete whatever is left over at the bottom in exactly one Delete()
    call, regardless of how many chunks that took or how the original
    matched rows were distributed. Requires these sheets to hold literal
    values only: a formula in the rewritten range would be flattened to a
    static value.
    """
    used = sheet.UsedRange
    first_row, first_col = used.Row, used.Column
    last_row = first_row + used.Rows.Count - 1
    last_col = first_col + used.Columns.Count - 1
    first_data_row = first_row + 1  # skip header row

    if last_row < first_data_row:
        return

    excel_col = date_col + 1  # Header-style 0-index -> Excel's 1-index
    date_idx = excel_col - first_col
    single_col = last_col == first_col

    # Whether Excel COM hands back naive or tz-aware datetimes for date
    # cells isn't consistent to rely on, and target may or may not carry
    # tzinfo itself (e.g. UTC from the CLI) -- strip both to naive so the
    # comparison below is never mixed-awareness.
    naive_target = target.replace(tzinfo=None) if target.tzinfo else target

    def _is_stale(row: tuple) -> bool:
        value = row[date_idx]
        if value is None:
            return True
        return (
            isinstance(value, datetime)
            and (value.replace(tzinfo=None) if value.tzinfo else value) > naive_target
        )

    row_count = last_row - first_data_row + 1
    write_cursor = first_data_row
    removed_count = 0
    chunk_count = 0
    read_seconds = 0.0
    write_seconds = 0.0

    read_start = first_data_row
    while read_start <= last_row:
        read_end = min(read_start + _CHUNK_ROWS - 1, last_row)
        chunk_count += 1

        t_read = time.perf_counter()
        chunk_range = sheet.Range(
            sheet.Cells(read_start, first_col), sheet.Cells(read_end, last_col)
        )
        rows = chunk_range.Value
        if read_end == read_start and single_col:
            rows = ((rows,),)  # a true 1x1 range collapses to a bare scalar
        read_seconds += time.perf_counter() - t_read

        kept_rows = [row for row in rows if not _is_stale(row)]
        removed_count += (read_end - read_start + 1) - len(kept_rows)

        if kept_rows:
            write_last_row = write_cursor + len(kept_rows) - 1
            # Nothing removed in this chunk, and the write cursor hasn't
            # fallen behind the read cursor from an earlier chunk either:
            # writing back would just be the same data to the same cells.
            unchanged = write_cursor == read_start and write_last_row == read_end
            if not unchanged:
                t_write = time.perf_counter()
                write_range = sheet.Range(
                    sheet.Cells(write_cursor, first_col),
                    sheet.Cells(write_last_row, last_col),
                )
                if write_last_row == write_cursor and single_col:
                    write_range.Value = kept_rows[0][0]  # true 1x1: bare scalar
                else:
                    write_range.Value = tuple(kept_rows)
                write_seconds += time.perf_counter() - t_write
            write_cursor = write_last_row + 1

        read_start = read_end + 1

    if removed_count == 0:
        logger.debug(
            f"[{sheet.Name}] scanned {row_count} rows in "
            f"{read_seconds:.2f}s over {chunk_count} chunk(s), nothing to remove"
        )
        return

    logger.debug(
        f"[timing] {sheet.Name}: scanned {row_count} rows in {read_seconds:.2f}s, "
        f"rewrote kept rows in {write_seconds:.2f}s, over {chunk_count} chunk(s); "
        f"keeping {write_cursor - first_data_row}, removing {removed_count}"
    )

    t_delete = time.perf_counter()
    sheet.Rows(f"{write_cursor}:{last_row}").Delete()
    logger.debug(
        f"[timing] {sheet.Name}: tail delete took {time.perf_counter() - t_delete:.2f}s"
    )


class CouldNotOpenFile(Exception):
    pass
