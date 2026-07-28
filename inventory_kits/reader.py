from typing import Generator, Iterable, Any 

import openpyxl as xl
from openpyxl.worksheet._read_only import ReadOnlyWorksheet
from openpyxl.workbook.workbook import Workbook
from decimal import Decimal

from collections import defaultdict

import json

class ExcelKitReader():
    def __init__(
        self, filename: str
    ):
        self.wb, self.data_source = self._initialize_data(filename)

    def read_all_kits(self) -> None:
        kits: dict[str, dict[str, int]] = defaultdict(dict)
        for row in self.readline():
            parent_sku = row[0]
            child_sku = row[1]
            kit_qty = row[2]
            kits[parent_sku][child_sku] = kit_qty
        print(kits)


    def readline(self) -> Generator[tuple]:
        yield from self._iter_raw()

    def _iter_raw(self) -> Iterable[tuple]:
        for i, raw in enumerate(self.data_source.iter_rows(values_only=True)):
            if i == 0:
                continue
            yield raw

    def _initialize_data(
        self, filename
    ) -> tuple[Workbook, ReadOnlyWorksheet]:
        
        wb = xl.load_workbook(
            filename=filename,
            read_only=True,
            data_only=True,
        )

        ws = wb.active
        if not isinstance(ws, ReadOnlyWorksheet):
            raise TypeError("Data must be in a Worksheet, not ChartSheet.")
    
        return wb, ws

    def close(self) -> None:
        """Free wb."""
        self.wb.close() 