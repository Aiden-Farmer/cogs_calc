from __future__ import annotations

from data.datarow_mutation_utils import split_kits
from data.datarows import RowLike, InventoryRow, InventoryDTO
from decimal import Decimal


class TestReader:
    def test_reader_handles_formula_cells(self): ...

    def test_reader_handles_password_protected_files(self): ...

    def test_reader_(self): ...

    def test_excel_reader_splits_kit_items(self):
        kit_ref = {"kit": {"comp1": 1, "comp2": 2}}

        def fake_iter_raw(self):
            dto = InventoryDTO()
            dto.sku = "kit"
            dto.base_sku = "kit"
            dto.inventory = Decimal(10)
            yield InventoryRow(dto)
            # {'sku': 'kit', 'base_sku': 'kit', 'inventory': 5}

        decorated = split_kits(fake_iter_raw, kit_ref=kit_ref)

        rows = list(decorated(RowLike))

        assert len(rows) == 2
        assert isinstance(rows[0], InventoryRow)
        assert rows[0].sku == "comp1"
        assert rows[0].qty == Decimal(10)

        assert rows[1].sku == "comp2"
        assert rows[1].qty == Decimal(20)

    def test_excel_reader_allows_non_kit_skus_through(self):
        kit_ref = {"kit": {"comp1": 1, "comp2": 2}}

        def fake_iter_raw(self):
            dto = InventoryDTO()
            dto.sku = "nonkit"
            dto.base_sku = "nonkit"
            dto.inventory = Decimal(10)
            yield InventoryRow(dto)
            # {'sku': 'kit', 'base_sku': 'kit', 'inventory': 5}

        decorated = split_kits(fake_iter_raw, kit_ref=kit_ref)

        rows = list(decorated(RowLike))

        assert len(rows) == 1
        assert isinstance(rows[0], InventoryRow)
        assert rows[0].sku == "nonkit"
        assert rows[0].qty == Decimal(10)
