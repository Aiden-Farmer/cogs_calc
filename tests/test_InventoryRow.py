from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

from src.data import FailedRow, Header, InventoryRow, LandedCostRow


class TestInventoryRowConstructor:
    """
        header = {
        'sku': 1,
        'base_sku': 0,
        'inventory': 2
    }
    """

    def test_inventory_row_from_row_constructor(self):
        h = Header.inventory_row(sku=0, base_sku=1, inventory=2)
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
        should_be_failed_row = InventoryRow.from_row(raw, h)
        assert isinstance(should_be_failed_row, FailedRow)
        assert isinstance(should_be_failed_row.error, ValueError)
        # assert should_be_failed_row.context == "Base must be the same as sku."

    def test_inventory_row_from_row_returns_none_when_base_sku_not_matching(self):
        h = Header.inventory_row(0, 1, 2)
        raw = []
        raw.append("sku")
        raw.append("some-other-sku")
        raw.append(100)

        fr = InventoryRow.from_row(raw, h)
        assert isinstance(fr, FailedRow)

    def test_inventory_row_handles_bad_inventory_datatype(self):
        """
        Expected Behavior is return None when invalid datatype and append failure dto record to cls.
        """
        h = Header.inventory_row(0, 1, 2)
        raw = []
        raw.append("sku")
        raw.append("sku")
        raw.append("typo")

        fr = InventoryRow.from_row(raw, h)
        assert isinstance(fr, FailedRow)

    def test_inventory_row_coerces_when_bad_sku_datatype(self):
        h = Header.inventory_row(0, 1, 2)
        raw = []
        raw.append(00000)
        raw.append(00000)
        raw.append(10)
        assert isinstance(InventoryRow.from_row(raw, h), InventoryRow)

    def test_inventory_row_rejects_sku_with_invalid_character(self):
        h = Header.inventory_row(0, 1, 2)
        raw = ["bad sku", "bad sku", 10]

        fr = InventoryRow.from_row(raw, h)

        assert isinstance(fr, FailedRow)


class TestHeaderRepr:
    def test_repr_includes_field_values(self):
        h = Header.inventory_row(sku=0, base_sku=1, inventory=2)

        assert repr(h) == f"Header({h.__dict__})"


class TestInventoryRowAllocation:
    @staticmethod
    def _create_row_instances():
        h = Header.inventory_row(0, 1, 2)
        cost = MagicMock(spec=LandedCostRow)
        cost.sku = "sku"
        cost.qty = 100
        cost.unit_cost = Decimal(1)
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
        """was failing because purchase that did not completely allocate Inventory Row unallocated amount led to verage cost recalculation based off of current total cost / Inventory row total, over-generalizing allcoated qty average cost"""
        inv_row, cost_row = self._create_row_instances()
        inv_row.allocate_from_landed_cost(cost_row)
        cost_total_cost = cost_row.unit_cost * cost_row.qty
        assert inv_row.total_cost == cost_total_cost
        assert inv_row.average_cost == cost_row.unit_cost

    def test_allocations_with_different_costs_impact_avco_proportional_to_units_allocated(
        self,
    ):
        inv_row, cost = self._create_row_instances()

        inv_row.allocate_from_landed_cost(cost)
        cost.unit_cost = Decimal(2)
        inv_row.allocate_from_landed_cost(cost)

        # Original cost Mock had unit cost=1, 100qty
        cost_total_cost = Decimal(300)

        assert inv_row.total_cost == cost_total_cost
        assert inv_row.average_cost == Decimal("1.5")

    def test_zero_qty_purchase_is_excluded_and_does_not_change_allocation(self):
        inv_row, cost = self._create_row_instances()
        cost.qty = 0

        inv_row.allocate_from_landed_cost(cost_row=cost)

        assert inv_row.excluded_dates == [cost.date]
        assert inv_row.unallocated == 200
        assert inv_row.total_cost == Decimal(0)

    def test_purchase_after_inventory_fully_allocated_is_excluded(self):
        inv_row, cost = self._create_row_instances()
        inv_row.unallocated = Decimal(0)

        inv_row.allocate_from_landed_cost(cost_row=cost)

        assert inv_row.excluded_dates == [cost.date]
        assert inv_row.total_cost == Decimal(0)

    def test_falls_back_to_total_cost_when_average_cost_division_is_undefined(self):
        """Regression test: a partial allocation that leaves qty - unallocated == 0
        used to raise decimal.InvalidOperation (DivisionUndefined) instead of falling
        back gracefully."""
        inv_row, cost = self._create_row_instances()
        # Contrived state to force the qty - unallocated == 0 denominator on a
        # partial (not full) allocation.
        inv_row.unallocated = inv_row.qty + Decimal(5)
        cost.qty = 5

        inv_row.allocate_from_landed_cost(cost_row=cost)

        assert inv_row.average_cost == inv_row.total_cost
        assert inv_row.total_cost == Decimal(5) * cost.unit_cost

    def test_export_returns_flattened_row_dict(self):
        inv_row, cost = self._create_row_instances()
        inv_row.allocate_from_landed_cost(cost_row=cost)

        exported = inv_row.export()

        assert exported["a"] == inv_row.sku
        assert exported["b"] == inv_row.qty
        assert exported["c"] == inv_row.unallocated
        assert exported["d"] == cost.date.strftime("%Y-%m-%d")
        assert exported["e"] == ""
        assert exported["f"] == inv_row.total_cost
        assert exported["g"] == inv_row.average_cost

    def test_repr_includes_key_fields(self):
        inv_row, _ = self._create_row_instances()

        r = repr(inv_row)

        assert "InventoryRow" in r
        assert "sku" in r
