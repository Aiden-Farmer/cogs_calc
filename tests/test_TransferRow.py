from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from src.data import FailedRow, Header
from src.transfers.transfer_rows import TransferRow


class TestTransferRowConstructor:
    def _create_data(self):
        data: list[Any] = [None for i in range(20)]
        data[0] = "from-sku"
        data[1] = "to-sku"
        data[2] = 5
        data[3] = datetime(2024, 6, 1)
        self.data = data

    def _header(self, **overrides):
        kwargs = {
            "from_sku": 0,
            "to_sku": 1,
            "qty": 2,
            "date": 3,
            "date_format": "%Y-%m-%d",
        }
        kwargs.update(overrides)
        return Header.transfer_row(**kwargs)

    def test_constructor_yields_transfer_row_with_valid_data(self):
        self._create_data()

        row = TransferRow.from_row(self.data, self._header())

        assert isinstance(row, TransferRow)
        assert row.from_sku == self.data[0]
        assert row.to_sku == self.data[1]
        assert row.qty == Decimal(self.data[2])
        assert row.date == self.data[3].replace(tzinfo=UTC)

    def test_constructor_yields_failedrow_when_qty_is_zero(self):
        self._create_data()
        self.data[2] = 0

        row = TransferRow.from_row(self.data, self._header())

        assert isinstance(row, FailedRow)

    def test_constructor_yields_failedrow_when_date_is_missing(self):
        self._create_data()
        self.data[3] = None

        row = TransferRow.from_row(self.data, self._header())

        assert isinstance(row, FailedRow)

    def test_constructor_handles_date_str(self):
        self._create_data()
        self.data[3] = "2024-06-01"

        row = TransferRow.from_row(self.data, self._header(date_format="%Y-%m-%d"))

        assert isinstance(row, TransferRow)
        assert row.date == datetime(2024, 6, 1, tzinfo=UTC)

    def test_constructor_yields_failedrow_when_date_str_does_not_match_format(self):
        self._create_data()
        self.data[3] = "not-a-date"

        row = TransferRow.from_row(self.data, self._header(date_format="%Y-%m-%d"))

        assert isinstance(row, FailedRow)

    def test_constructor_yields_failedrow_on_incompatible_types(self):
        self._create_data()
        self.data[2] = "not-a-number"

        row = TransferRow.from_row(self.data, self._header())

        assert isinstance(row, FailedRow)

    def test_constructor_keeps_naive_datetime_cell_as_utc_not_local(self):
        # dt.strptime(...).astimezone() would reinterpret a naive value as
        # being in the *system's local* timezone before converting; a
        # datetime already handed back by openpyxl should just be stamped
        # UTC directly, not shifted.
        self._create_data()
        self.data[3] = datetime(2024, 6, 1, 12, 0)

        row = TransferRow.from_row(self.data, self._header())

        assert isinstance(row, TransferRow)
        assert row.date == datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
