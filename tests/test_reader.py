from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from data import InventoryRow, LandedCostRow
from data.datarow_mutation_utils import split_kits

# Private submodules
from data.datarows import InventoryDTO, LandedCostDTO, RowLike


class TestReader:
    @staticmethod
    def _fake_kit_ref():
        return {
            "kit": {
                "comp1": {
                    "qty": 1,
                    "cost": Decimal(1),
                    "pc_of_total_cost": Decimal(0.25),
                },
                "comp2": {
                    "qty": 1,
                    "cost": Decimal(2),
                    "pc_of_total_cost": Decimal(0.75),
                },
            }
        }

    @staticmethod
    def fake_purchase_iter_raw(rt: type[RowLike]):
        dto = LandedCostDTO()
        dto.sku = "kit"
        dto.qty = Decimal(10)
        dto.unit_cost = Decimal(3)
        dto.date = datetime(2026, 1, 1)
        yield LandedCostRow(dto)

    @staticmethod
    def fake_inventory_iter_raw(rt: type[RowLike]):
        dto = InventoryDTO()
        dto.sku = "nonkit"
        dto.base_sku = "nonkit"
        dto.inventory = Decimal(10)
        yield InventoryRow(dto)

    def test_reader_handles_formula_cells(self): ...

    def test_reader_handles_password_protected_files(self): ...

    def test_reader_(self): ...

    def test_excel_reader_allows_non_kit_skus_through(self):
        kit_ref = self._fake_kit_ref()

        decorated = split_kits(self.fake_inventory_iter_raw, kit_ref=kit_ref)

        rows = list(decorated(RowLike))

        assert len(rows) == 1
        assert isinstance(rows[0], InventoryRow)
        assert rows[0].sku == "nonkit"
        assert rows[0].qty == Decimal(10)

    def test_excel_reader_allocates_landed_cost_from_kits(self):
        kit_ref = self._fake_kit_ref()

        decorated = split_kits(
            self.fake_purchase_iter_raw, kit_ref=kit_ref, ALLOCATE_COMP_COST=0
        )

        rows = list(decorated(RowLike))

        assert len(rows) == 2
        assert isinstance(rows[0], LandedCostRow)
        assert rows[0].sku == "comp1"
        assert rows[0].unit_cost == Decimal(0.75)

        assert isinstance(rows[1], LandedCostRow)
        assert rows[1].sku == "comp2"
        assert rows[1].unit_cost == Decimal(2.25)

    def test_reader_allocates_kit_components_by_quantity(self):
        kit_ref = {
            "kit": {
                "comp1": {
                    "qty": 1,
                    "cost": Decimal("2.0"),
                    "pc_of_total_cost": Decimal(".50"),
                },
                "comp2": {
                    "qty": 2,
                    "cost": Decimal(1.0),
                    "pc_of_total_cost": Decimal("0.25"),
                },
            }
        }

        def fake_iter_raw(self):
            dto = InventoryDTO()
            dto.sku = "kit"
            dto.base_sku = "kit"
            dto.inventory = Decimal(10)
            yield InventoryRow(dto)
            # {'sku': 'kit', 'base_sku': 'kit', 'inventory': 5}

            dto = InventoryDTO()
            dto.sku = "comp1"
            dto.base_sku = "comp1"
            dto.inventory = Decimal(5)
            yield InventoryRow(dto)

        # Use
        decorated = split_kits(fake_iter_raw, kit_ref=kit_ref, ALLOCATE_COMP_COST=1)

        rows = list(decorated(RowLike))

        # Reader is dumb and doesn't know it previously returned comp1 as kit element, expected behaviour is 2 InventoryRows when sku is both kit component and sku itemself,
        # consumer of reader is expected to handle
        assert len(rows) == 3
        assert isinstance(rows[0], InventoryRow)
        assert rows[0].sku == "comp1"
        assert rows[0].qty == Decimal(10)

        assert isinstance(rows[1], InventoryRow)
        assert rows[1].sku == "comp2"
        assert rows[1].qty == Decimal(20)

        assert isinstance(rows[2], InventoryRow)
        assert rows[2].sku == "comp1"
        assert rows[2].qty == Decimal(5)
