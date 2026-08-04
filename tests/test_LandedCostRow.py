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


r"""
Traceback (most recent call last):
  File "C:\Users\accou\cogs_calc\main.py", line 150, in <module>
    calculate_all_lineitems_average_cost_from_excel(
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^
        landed_cost_filepath=args.purchase_file,
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<2 lines>...
        inventory_sheet_name=args.inventory_sheet_name,
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "C:\Users\accou\cogs_calc\main.py", line 78, in calculate_all_lineitems_average_cost_from_excel
    inventory[cost_row.sku].allocate_from_landed_cost(cost_row)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^
  File "C:\Users\accou\cogs_calc\data\datarows.py", line 122, in allocate_from_landed_cost
    self.average_cost = self.total_cost / (self.qty - self.unallocated)
                        ~~~~~~~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
decimal.InvalidOperation: [<class 'decimal.DivisionUndefined'>]
"""
