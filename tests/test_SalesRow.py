from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.data import FailedRow, Header, SalesRow


class TestSalesRowConstructor:
    def _create_data(self):
        data: list[Any] = [None for i in range(20)]
        data[0] = "sku"
        data[1] = "Amazon"
        data[2] = 3
        self.data = data

    def test_constructor_yields_sales_row_with_valid_data(self):
        self._create_data()

        h = Header.sales_row(sku=0, channel=1, qty=2)
        row = SalesRow.from_row(self.data, h)

        assert isinstance(row, SalesRow)
        assert row.sku == self.data[0]
        assert row.channel == self.data[1]
        assert row.qty == Decimal(self.data[2])

    def test_constructor_yields_failedrow_when_qty_is_zero(self):
        self._create_data()
        self.data[2] = 0

        h = Header.sales_row(sku=0, channel=1, qty=2)
        row = SalesRow.from_row(self.data, h)

        assert isinstance(row, FailedRow)

    def test_constructor_yields_failedrow_on_incompatible_types(self):
        self._create_data()
        self.data[2] = "not-a-number"

        h = Header.sales_row(sku=0, channel=1, qty=2)
        row = SalesRow.from_row(self.data, h)

        assert isinstance(row, FailedRow)

    def test_constructor_yields_failedrow_when_channel_is_blank(self):
        self._create_data()
        self.data[1] = ""

        h = Header.sales_row(sku=0, channel=1, qty=2)
        row = SalesRow.from_row(self.data, h)

        assert isinstance(row, FailedRow)
        assert row.context == "incomplete data in row."


class TestSalesRowMisc:
    def _make_row(self):
        h = Header.sales_row(sku=0, channel=1, qty=2)
        raw: list[Any] = [None] * 3
        raw[0] = "sku"
        raw[1] = "Amazon"
        raw[2] = 5
        row = SalesRow.from_row(raw, h)
        assert isinstance(row, SalesRow)
        return row

    def test_repr_includes_key_fields(self):
        row = self._make_row()

        r = repr(row)

        assert "sku" in r
        assert "Amazon" in r
