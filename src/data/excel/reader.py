from __future__ import annotations

import io
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from getpass import getpass
from typing import TypeVar
from warnings import filterwarnings
from zipfile import BadZipFile

import msoffcrypto
import openpyxl as xl
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet._read_only import ReadOnlyWorksheet

from ..datarow_mutation_utils import split_kits
from ..datarows import RowLike
from ..reader import AbstractReader, FailedRow, Header

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


def remove_wb_dates_after_target(self, target: datetime):
    # release resource so we can reopen with write permissions.
    raise NotImplementedError


class CouldNotOpenFile(Exception):
    pass
