from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from unittest.mock import MagicMock
import pytest

from data import *

class TestInventoryRowConstructor:
    """
        header = {
        'sku': 1,
        'base_sku': 0,
        'inventory': 2
    }
    """

    def test_inventory_row_from_row_constructor(self):
        h = Header.inventory_row(0, 1, 2)
        # row can be any object that implements __getitem__?
        raw: list[Any] = [0, 0, 0]
        raw[0] = "test_sku"
        raw[1] = "test_sku"
        raw[2] = 100

        assert isinstance(InventoryRow.from_row(raw, h), InventoryRow)

    def test_inventory_row_from_row_returns_none_when_input_has_no_sku(self):
        h = Header.inventory_row(0, 1, 2)
        raw = []
        raw.append(None)
        raw.append("sku")
        raw.append(2)
        should_be_none = InventoryRow.from_row(raw, h)
        assert should_be_none is None

    def test_inventory_row_from_row_returns_none_when_base_sku_not_matching(self):
        h = Header.inventory_row(0, 1, 2)
        raw = []
        raw.append("sku")
        raw.append("some-other-sku")
        raw.append(100)

        should_be_none = InventoryRow.from_row(raw, h)
        assert should_be_none is None

    def test_inventory_row_raises_when_bad_inventory_datatype(self):
        h = Header.inventory_row(0, 1, 2)
        raw = []
        raw.append("sku")
        raw.append("sku")
        raw.append("typo")

        with pytest.raises(InvalidOperation):
            InventoryRow.from_row(raw, h)

    def test_inventory_row_coerces_when_bad_sku_datatype(self):
        h = Header.inventory_row(0, 1, 2)
        raw = []
        raw.append(00000)
        raw.append(00000)
        raw.append(10)
        assert isinstance(InventoryRow.from_row(raw, h), InventoryRow)


class TestInventoryRowAllocation:
    @staticmethod
    def _create_row_instances():
        h = Header.inventory_row(0, 1, 2)
        cost = MagicMock(spec=LandedCostRow)
        cost.sku = "sku"
        cost.qty = 100
        cost.unit_cost = Decimal("1")
        cost.date = datetime(2020, 12, 20)

        raw = []
        raw.append("sku")
        raw.append("sku")
        raw.append(200)
        inv_row = InventoryRow.from_row(raw, h)
        assert isinstance(inv_row, InventoryRow)
        return (inv_row, cost)

    def test_partial_allocation_from_landed_cost_decrements_unallocated(self):
        inv_row, cost = self._create_row_instances()

        assert inv_row.unallocated == 200
        inv_row.allocate_from_landed_cost(cost_row=cost)
        assert inv_row.unallocated == 100

    def test_allocation_from_landed_cost_appends_lc_purchase_date_to_inv_row_purchase_dates(
        self,
    ):
        inv_row, cost = self._create_row_instances()

        assert len(inv_row.purchase_dates) == 0
        inv_row.allocate_from_landed_cost(cost_row=cost)
        assert len(inv_row.purchase_dates) == 1
        assert inv_row.purchase_dates[0] == cost.date

    def test_allocation_from_purchase_greater_than_inventory_only_allocates_inventory(
        self,
    ):
        inv_row, cost = self._create_row_instances()
        cost.qty = 500

        inv_row.allocate_from_landed_cost(cost_row=cost)
        assert inv_row.unallocated == 0

    def test_allocation_impacts_cost(self):
        inv_row, cost = self._create_row_instances()
        inv_row.allocate_from_landed_cost(cost)
        cost_total_cost = cost.unit_cost * cost.qty
        assert inv_row.total_cost == cost_total_cost
        assert inv_row.average_cost == cost.unit_cost

    def test_allocations_with_different_costs_impact_avco_proportional_to_units_allocated(
        self,
    ):
        inv_row, cost = self._create_row_instances()

        inv_row.allocate_from_landed_cost(cost)
        cost.unit_cost = Decimal("2")
        inv_row.allocate_from_landed_cost(cost)

        # Original cost Mock had unit cost=1, 100qty
        cost_total_cost = Decimal("300")

        assert inv_row.total_cost == cost_total_cost
        assert inv_row.average_cost == Decimal("1.5")
