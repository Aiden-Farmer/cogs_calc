import pytest
import random
from typing import Any
from datetime import datetime
from decimal import Decimal

from data import LandedCostRow, InventoryRow, Header

class TestLandedCostRowConstructor:
    
    def _create_data(self):
        data: list[Any] = [None for i in range(20)]
        data[0] = 'sku'
        data[2] = 200
        data[3] = float(2.0)
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

    def test_constructor_handles_date_str(self):
        self._create_data()
        self.data[10] = '2020-12-31'
        h = Header.landed_cost(sku=0, qty=2, unit_cost=3, date=10, date_format="%Y-%m-%d")
        lc = LandedCostRow.from_row(self.data, h)

        assert lc
        assert lc.date == datetime(year=2020, month=12, day=31)





