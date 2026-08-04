from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from src.data import FailedRow, Header, LandedCostRow


class TestLandedCostRowConstructor:
    def _create_data(self):
        data: list[Any] = [None for i in range(20)]
        data[0] = "sku"
        data[2] = 200
        data[3] = 2.0
        data[4] = datetime.min
        self.data = data

    def test_constructor_yields_landed_cost_object_with_valid_data(self):
        self._create_data()

        h = Header.landed_cost(sku=0, qty=2, unit_cost=3, date=4)
        lc = LandedCostRow.from_row(self.data, h)

        assert isinstance(lc, LandedCostRow)
        assert lc.date == self.data[4]
        assert lc.unit_cost == Decimal(self.data[3])
        assert lc.qty == self.data[2]
        assert lc.sku == self.data[0]

    def test_constructor_yields_FailedRow_when_no_purchase_qty(self):
        self._create_data()
        self.data[2] = 0

        h = Header.landed_cost(sku=0, qty=2, unit_cost=4, date=4)
        lc = LandedCostRow.from_row(self.data, h)

        assert isinstance(lc, FailedRow)

    def test_constructor_handles_date_str(self):
        self._create_data()
        self.data[10] = "2020-12-31"
        h = Header.landed_cost(
            sku=0,
            qty=2,
            unit_cost=3,
            date=10,
            date_format="%Y-%m-%d",
        )
        lc = LandedCostRow.from_row(self.data, h)

        assert isinstance(lc, LandedCostRow)
        assert lc.date == datetime(year=2020, month=12, day=31)

    def test_constructor_yields_failedrow_on_incompatible_types(self):
        self._create_data()
        self.data[2] = "not-a-number"

        h = Header.landed_cost(sku=0, qty=2, unit_cost=3, date=4)
        lc = LandedCostRow.from_row(self.data, h)

        assert isinstance(lc, FailedRow)

    def test_constructor_yields_failedrow_when_date_is_missing(self):
        self._create_data()
        self.data[4] = None

        h = Header.landed_cost(sku=0, qty=2, unit_cost=3, date=4)
        lc = LandedCostRow.from_row(self.data, h)

        assert isinstance(lc, FailedRow)

    def test_constructor_yields_failedrow_when_date_str_does_not_match_format(self):
        self._create_data()
        self.data[10] = "not-a-date"
        h = Header.landed_cost(
            sku=0, qty=2, unit_cost=3, date=10, date_format="%Y-%m-%d"
        )

        lc = LandedCostRow.from_row(self.data, h)

        assert isinstance(lc, FailedRow)

    def test_constructor_yields_failedrow_when_unit_cost_is_zero(self):
        self._create_data()
        self.data[3] = 0

        h = Header.landed_cost(sku=0, qty=2, unit_cost=3, date=4)
        lc = LandedCostRow.from_row(self.data, h)

        assert isinstance(lc, FailedRow)
        assert lc.context == "incomplete data in row."


class TestLandedCostRowMisc:
    def _make_row(self):
        h = Header.landed_cost(sku=0, qty=2, unit_cost=3, date=4)
        raw: list[Any] = [None] * 5
        raw[0] = "sku"
        raw[2] = 10
        raw[3] = 2.5
        raw[4] = datetime(2024, 1, 1)
        row = LandedCostRow.from_row(raw, h)
        assert isinstance(row, LandedCostRow)
        return row

    def test_repr_includes_key_fields(self):
        row = self._make_row()

        r = repr(row)

        assert "sku" in r
        assert str(row.qty) in r

    def test_sort_key_returns_date(self):
        row = self._make_row()

        assert LandedCostRow.sort_key(row) == row.date
