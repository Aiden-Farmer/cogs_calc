from collections.abc import Iterable

import openpyxl as xl
from openpyxl.workbook import Workbook
from openpyxl.worksheet._read_only import ReadOnlyWorksheet

from src.data import DataSourceError, FailedRow, Header
from .transfer_rows import TransferRow 

_HEADER_ROWS = {0}

class TransferFileReader:
    def __init__(self, filename, header: Header):
        self.header = header
        self.wb, self.data_source = self._initialize_data(filename)

    def readline(self) -> Iterable[TransferRow | FailedRow]:
        for raw in self._iter():
            yield TransferRow.from_row(raw, header = self.header)


    def _iter(self, h_rows=_HEADER_ROWS) -> Iterable[tuple]:
        """Needless wrapper func?"""
        """ Abstracts reading records so readline can call a method of just data, 
        and not worry about shape"""

        for i, raw in enumerate(self.data_source.iter_rows(values_only=True)):
            if i in h_rows:
                continue
            yield raw

    def _initialize_data(self, filename) -> tuple[Workbook, ReadOnlyWorksheet]:
        wb = xl.load_workbook(
            filename=filename,
            read_only=True,
            data_only=True,
        )

        if len(wb.sheetnames) > 1:
            raise DataSourceError("Transfers File must have exactly one sheet.")

        ws = wb.active
        if not isinstance(ws, ReadOnlyWorksheet):
            raise TypeError(f"Data must be in Worksgheet, not {type(ws)}")

        return wb, ws

    def close(self, save_new=False) -> None:
        """Free wb"""
        if save_new:
            raise NotImplementedError
        self.wb.close()
