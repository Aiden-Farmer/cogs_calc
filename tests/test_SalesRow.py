from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.data import FailedRow, Header, SalesRow


class TestSalesRowConstructor:
    def _create_data(self):
        # sku, Amazon qty, eBay qty
        data: list[Any] = [None for i in range(20)]
        data[0] = "sku"
        data[1] = 3
        data[2] = 5
        self.data = data

    def _header(self, **overrides):
        channel_columns = {"Amazon": 1, "eBay": 2}
        channel_columns.update(overrides)
        return Header.sales_row(sku=0, channel_columns=channel_columns)

    def test_constructor_yields_sales_row_with_qty_per_channel(self):
        self._create_data()

        row = SalesRow.from_row(self.data, self._header())

        assert isinstance(row, SalesRow)
        assert row.sku == "sku"
        assert row.qty == {"Amazon": Decimal(3), "eBay": Decimal(5)}

    def test_blank_channel_columns_are_omitted_not_failed(self):
        self._create_data()
        self.data[2] = None  # sku didn't sell on eBay this period

        row = SalesRow.from_row(self.data, self._header())

        assert isinstance(row, SalesRow)
        assert row.qty == {"Amazon": Decimal(3)}

    def test_zero_channel_qty_is_omitted(self):
        self._create_data()
        self.data[2] = 0

        row = SalesRow.from_row(self.data, self._header())

        assert isinstance(row, SalesRow)
        assert row.qty == {"Amazon": Decimal(3)}

    def test_all_channels_blank_yields_empty_qty(self):
        self._create_data()
        self.data[1] = None
        self.data[2] = None

        row = SalesRow.from_row(self.data, self._header())

        assert isinstance(row, SalesRow)
        assert row.qty == {}

    def test_yields_failedrow_when_sku_is_blank(self):
        self._create_data()
        self.data[0] = ""

        row = SalesRow.from_row(self.data, self._header())

        assert isinstance(row, FailedRow)

    def test_yields_failedrow_when_a_channel_qty_is_negative(self):
        self._create_data()
        self.data[2] = -1

        row = SalesRow.from_row(self.data, self._header())

        assert isinstance(row, FailedRow)

    def test_yields_failedrow_when_a_channel_qty_is_not_a_number(self):
        self._create_data()
        self.data[2] = "not-a-number"

        row = SalesRow.from_row(self.data, self._header())

        assert isinstance(row, FailedRow)


class TestSalesRowMisc:
    def _make_row(self):
        h = Header.sales_row(sku=0, channel_columns={"Amazon": 1})
        raw: list[Any] = [None] * 2
        raw[0] = "sku"
        raw[1] = 5
        row = SalesRow.from_row(raw, h)
        assert isinstance(row, SalesRow)
        return row

    def test_repr_includes_key_fields(self):
        row = self._make_row()

        r = repr(row)

        assert "sku" in r
        assert "Amazon" in r
