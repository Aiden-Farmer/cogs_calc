from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import openpyxl
import pytest

from src.adapters import (
    allocate_landed_costs,
    build_inventory,
    build_transfers,
    give_reader,
    give_transfer_reader,
    record_sales,
    write_outfile,
)
from src.data import (
    DataSourceError,
    FailedRow,
    Header,
    InventoryRow,
    LandedCostRow,
    SalesData,
    SalesRow,
)
from src.data.datarows import InventoryDTO, LandedCostDTO, SalesDTO
from src.data.excel.reader import ExcelFileReader
from src.transfers.reader import TransferFileReader
from src.transfers.transfer_rows import TransferDTO, TransferRow


class _FakeReader:
    """Minimal stand-in for excel.Reader[T] -- build_inventory/allocate_landed_costs
    only ever call .readline(), so a real workbook isn't needed to exercise them."""

    def __init__(self, rows):
        self._rows = rows

    def readline(self):
        return iter(self._rows)


def _inventory_row(sku: str, qty: int) -> InventoryRow:
    dto = InventoryDTO()
    dto.sku = sku
    dto.base_sku = sku
    dto.inventory = Decimal(qty)
    return InventoryRow(dto)


def _landed_cost_row(sku: str, qty: int, unit_cost: int) -> LandedCostRow:
    dto = LandedCostDTO()
    dto.sku = sku
    dto.qty = Decimal(qty)
    dto.unit_cost = Decimal(unit_cost)
    dto.date = datetime(2024, 1, 1)
    return LandedCostRow(dto)


def _sales_row(sku: str, qty: dict[str, int]) -> SalesRow:
    dto = SalesDTO()
    dto.sku = sku
    dto.qty = {c: Decimal(q) for c, q in qty.items()}
    return SalesRow(dto)


def _transfer_row(from_sku: str, to_sku: str, qty: int) -> TransferRow:
    dto = TransferDTO()
    dto.from_sku = from_sku
    dto.to_sku = to_sku
    dto.qty = Decimal(qty)
    dto.date = datetime(2024, 1, 1)
    return TransferRow(dto)


class TestGiveReader:
    def test_raises_typeerror_when_file_is_not_xlsx(self):
        with pytest.raises(TypeError):
            give_reader(
                file_path="inventory.csv",
                sheet_name="Sheet1",
                header=Header.inventory_row(sku=0, base_sku=1, inventory=2),
                return_type=InventoryRow,
            )

    def test_wires_reader_with_requested_header_and_return_type(self, tmp_path):
        wb = openpyxl.Workbook()
        wb.active.title = "Inventory"
        path = tmp_path / "inventory.xlsx"
        wb.save(path)

        header = Header.inventory_row(sku=0, base_sku=1, inventory=2)
        reader = give_reader(
            file_path=str(path),
            sheet_name="Inventory",
            header=header,
            return_type=InventoryRow,
        )

        assert isinstance(reader, ExcelFileReader)
        assert reader.rt is InventoryRow
        assert reader.header is header


class TestGiveTransferReader:
    def test_raises_typeerror_when_file_is_not_xlsx(self):
        with pytest.raises(TypeError):
            give_transfer_reader(
                file_path="transfers.csv",
                sheet_name="Sheet1",
                header=Header.transfer_row(
                    from_sku=0, to_sku=1, qty=2, date=3, date_format="%Y-%m-%d"
                ),
            )

    def test_asserts_sheet_name_is_required(self):
        with pytest.raises(AssertionError):
            give_transfer_reader(
                file_path="transfers.xlsx",
                sheet_name="",
                header=Header.transfer_row(
                    from_sku=0, to_sku=1, qty=2, date=3, date_format="%Y-%m-%d"
                ),
            )

    def test_wires_reader_to_the_named_sheet(self, tmp_path):
        wb = openpyxl.Workbook()
        wb.active.title = "Sheet1"
        transfers_sheet = wb.create_sheet("Transfers")
        transfers_sheet.append(["header"])
        transfers_sheet.append(["sku-a", "sku-b", 3, "2024-06-01"])
        path = tmp_path / "transfers.xlsx"
        wb.save(path)

        header = Header.transfer_row(
            from_sku=0, to_sku=1, qty=2, date=3, date_format="%Y-%m-%d"
        )
        reader = give_transfer_reader(
            file_path=str(path), sheet_name="Transfers", header=header
        )

        assert isinstance(reader, TransferFileReader)
        rows = list(reader.readline())
        assert len(rows) == 1
        assert rows[0].from_sku == "sku-a"


class TestBuildInventory:
    def test_aggregates_duplicate_skus(self):
        rows = [_inventory_row("sku-a", 10), _inventory_row("sku-a", 5)]

        inventory, failed = build_inventory(_FakeReader(rows))

        assert failed == []
        assert inventory["sku-a"].qty == Decimal(15)
        # unallocated is reset to the newly-merged total, per build_inventory's merge step
        assert inventory["sku-a"].unallocated == Decimal(15)

    def test_collects_failed_rows_instead_of_raising(self):
        good = _inventory_row("sku-a", 10)
        bad = FailedRow(row=["bad"], error=ValueError(), context="bad row")

        inventory, failed = build_inventory(_FakeReader([good, bad]))

        assert list(inventory) == ["sku-a"]
        assert failed == [bad]

    def test_raises_datasourceerror_when_no_rows_survive(self):
        bad = FailedRow(row=["bad"], error=ValueError(), context="bad row")

        with pytest.raises(DataSourceError):
            build_inventory(_FakeReader([bad]))


class TestBuildTransfers:
    def test_creates_entry_for_new_from_sku(self):
        row = _transfer_row("sku-a", "sku-b", qty=5)

        transfers, failed = build_transfers(_FakeReader([row]))

        assert failed == []
        assert transfers["sku-a"] is row

    def test_accumulates_qty_for_repeated_from_sku_with_same_to_sku(self):
        # Regression test: build_transfers used to index the transfers
        # dict (keyed by from_sku) by to_sku instead when consolidating a
        # repeated from_sku, which raised KeyError/DataSourceError instead
        # of accumulating qty as intended.
        first = _transfer_row("sku-a", "sku-b", qty=5)
        second = _transfer_row("sku-a", "sku-b", qty=3)

        transfers, failed = build_transfers(_FakeReader([first, second]))

        assert failed == []
        assert transfers["sku-a"].qty == Decimal(8)

    def test_raises_datasourceerror_when_same_from_sku_maps_to_different_to_sku(self):
        first = _transfer_row("sku-a", "sku-b", qty=5)
        conflicting = _transfer_row("sku-a", "sku-c", qty=3)

        with pytest.raises(DataSourceError):
            build_transfers(_FakeReader([first, conflicting]))

    def test_collects_failedrow_from_reader_instead_of_raising(self):
        bad = FailedRow(row=["bad"], error=ValueError(), context="bad row")

        transfers, failed = build_transfers(_FakeReader([bad]))

        assert transfers == {}
        assert failed == [bad]


class TestRecordSales:
    def test_records_sale_qty_against_matching_inventory_row(self):
        inv_row = _inventory_row("sku-a", 10)
        inventory = {"sku-a": inv_row}
        sale_row = _sales_row("sku-a", {"Amazon": 3})

        failed = record_sales(_FakeReader([sale_row]), inventory)

        assert failed == []
        assert inv_row.sales.sales_qty["Amazon"] == 3
        assert inv_row.sales.total_sales == 3

    def test_records_qty_for_every_channel_present_on_the_row(self):
        inv_row = _inventory_row("sku-a", 10)
        inventory = {"sku-a": inv_row}
        sale_row = _sales_row("sku-a", {"Amazon": 3, "eBay": 2})

        failed = record_sales(_FakeReader([sale_row]), inventory)

        assert failed == []
        assert inv_row.sales.sales_qty["Amazon"] == 3
        assert inv_row.sales.sales_qty["eBay"] == 2
        assert inv_row.sales.total_sales == 5

    def test_sale_for_sku_not_in_inventory_is_recorded_as_failed(self):
        sale_row = _sales_row("missing-sku", {"Amazon": 3})

        failed = record_sales(_FakeReader([sale_row]), {})

        assert len(failed) == 1
        assert failed[0].row is sale_row
        assert failed[0].context == "Sale for item that is not in inventory."

    def test_collects_failedrow_from_reader_instead_of_raising(self):
        bad = FailedRow(row=["bad"], error=ValueError(), context="bad row")

        failed = record_sales(_FakeReader([bad]), {})

        assert failed == [bad]


class TestAllocateLandedCosts:
    def test_allocates_cost_to_matching_inventory_row(self):
        inv_row = _inventory_row("sku-a", 10)
        inventory = {"sku-a": inv_row}
        cost_row = _landed_cost_row("sku-a", qty=10, unit_cost=2)

        failed = allocate_landed_costs(_FakeReader([cost_row]), inventory)

        assert failed == []
        assert inv_row.unallocated == Decimal(0)
        assert inv_row.total_cost == Decimal(20)

    def test_purchase_for_sku_not_in_inventory_is_recorded_as_failed(self):
        cost_row = _landed_cost_row("missing-sku", qty=10, unit_cost=2)

        failed = allocate_landed_costs(_FakeReader([cost_row]), {})

        assert len(failed) == 1
        assert failed[0].row is cost_row
        assert failed[0].context == "Purchase for item that is not in inventory."

    def test_collects_failedrow_from_reader_instead_of_raising(self):
        bad = FailedRow(row=["bad"], error=ValueError(), context="bad row")

        failed = allocate_landed_costs(_FakeReader([bad]), {})

        assert failed == [bad]

    def test_transfer_sku_with_remaining_unallocated_stock_allocates_once_not_twice(
        self,
    ):
        # Regression test: _allocator used to fall through to an
        # unconditional final allocate_from_landed_cost() call even after
        # already allocating inside the transfer branch, double-counting
        # the same purchase against the same row.
        source_row = _inventory_row("sku-a", 10)
        dest_row = _inventory_row("sku-b", 20)
        inventory = {"sku-a": source_row, "sku-b": dest_row}
        transfers = {"sku-a": _transfer_row("sku-a", "sku-b", qty=5)}
        cost_row = _landed_cost_row("sku-a", qty=4, unit_cost=2)

        failed = allocate_landed_costs(_FakeReader([cost_row]), inventory, transfers)

        assert failed == []
        assert source_row.unallocated == Decimal(6)
        assert source_row.total_cost == Decimal(8)  # 4 * 2, not doubled
        assert dest_row.unallocated == Decimal(20)  # untouched
        assert transfers["sku-a"].qty == Decimal(5)  # untouched

    def test_transfer_sku_with_exhausted_source_redirects_to_destination_only(self):
        # Regression test: the same unconditional final call also meant a
        # redirected purchase got spuriously credited a second time onto
        # the (already fully-allocated) source row too.
        source_row = _inventory_row("sku-a", 0)  # already fully allocated
        dest_row = _inventory_row("sku-b", 20)
        inventory = {"sku-a": source_row, "sku-b": dest_row}
        transfers = {"sku-a": _transfer_row("sku-a", "sku-b", qty=5)}
        cost_row = _landed_cost_row("sku-a", qty=3, unit_cost=2)

        failed = allocate_landed_costs(_FakeReader([cost_row]), inventory, transfers)

        assert failed == []
        assert dest_row.unallocated == Decimal(17)
        assert dest_row.total_cost == Decimal(6)  # 3 * 2
        assert source_row.total_cost == Decimal(0)  # not spuriously credited
        assert transfers["sku-a"].qty == Decimal(2)  # 5 - 3 remaining

    def test_transfer_qty_exhausted_exactly_removes_transfer_entry(self):
        source_row = _inventory_row("sku-a", 0)
        dest_row = _inventory_row("sku-b", 20)
        inventory = {"sku-a": source_row, "sku-b": dest_row}
        transfers = {"sku-a": _transfer_row("sku-a", "sku-b", qty=3)}
        cost_row = _landed_cost_row("sku-a", qty=3, unit_cost=2)

        allocate_landed_costs(_FakeReader([cost_row]), inventory, transfers)

        assert "sku-a" not in transfers

    def test_purchase_qty_exceeding_remaining_transfer_qty_allocates_leftover_to_source(
        self,
    ):
        # Regression test: cost_row.qty was overwritten by min(qty,
        # transfer_row.qty) with no path left to allocate the excess
        # anywhere, silently dropping it instead of crediting it back to
        # the source sku once the transfer budget is exhausted.
        source_row = _inventory_row("sku-a", 0)  # already fully allocated
        dest_row = _inventory_row("sku-b", 20)
        inventory = {"sku-a": source_row, "sku-b": dest_row}
        transfers = {"sku-a": _transfer_row("sku-a", "sku-b", qty=3)}
        cost_row = _landed_cost_row("sku-a", qty=5, unit_cost=2)  # 5 > 3 remaining

        allocate_landed_costs(_FakeReader([cost_row]), inventory, transfers)

        assert dest_row.unallocated == Decimal(17)  # 20 - 3 redirected
        assert dest_row.total_cost == Decimal(6)  # 3 * 2
        assert "sku-a" not in transfers  # transfer budget exhausted
        # leftover 2 units routed to source_row, which has 0 unallocated,
        # so allocate_from_landed_cost records it via the sales/excluded
        # path rather than growing total_cost against nonexistent stock.
        assert source_row.total_cost == Decimal(0)
        assert source_row.excluded_dates == [cost_row.date]


class TestWriteOutfile:
    def test_header_includes_one_column_per_sales_channel(self, tmp_path):
        inv_row = _inventory_row("sku-a", 10)
        outfile = tmp_path / "outfile.xlsx"

        with patch("src.adapters.startfile"):
            write_outfile({"sku-a": inv_row}, outfile_name=str(outfile))

        wb = openpyxl.load_workbook(outfile)
        header = [c.value for c in next(wb.active.iter_rows(max_row=1))]

        assert header[:7] == [
            "SKU",
            "Inventory Cost",
            "Unallocated",
            "Dates Received",
            "Dates received not counting against Average Cost",
            "Total Cost",
            "Average Cost",
        ]
        channels = list(SalesData().sales_qty.keys())
        assert header[7 : 7 + len(channels)] == channels
        assert header[7 + len(channels) :] == [f"{c} Value" for c in channels]

    def test_writes_recorded_sales_qty_in_the_matching_channel_column(self, tmp_path):
        inv_row = _inventory_row("sku-a", 10)
        inv_row.record_sale("Amazon", 4)
        inv_row.record_sale("eBay", 2)
        outfile = tmp_path / "outfile.xlsx"

        with patch("src.adapters.startfile"):
            write_outfile({"sku-a": inv_row}, outfile_name=str(outfile))

        wb = openpyxl.load_workbook(outfile)
        header = [c.value for c in next(wb.active.iter_rows(max_row=1, max_col=30))]
        data_row = [
            c.value for c in next(wb.active.iter_rows(min_row=2, max_row=2, max_col=30))
        ]
        by_header = dict(zip(header, data_row, strict=False))

        assert by_header["Amazon"] == 4
        assert by_header["eBay"] == 2
        assert by_header["Etsy"] == 0

    def test_writes_computed_sales_value_in_the_matching_value_column(self, tmp_path):
        inv_row = _inventory_row("sku-a", 0)  # unallocated starts at 0
        inv_row.record_sale("Amazon", 5)
        cost_row = _landed_cost_row("sku-a", qty=5, unit_cost=2)
        inv_row.allocate_from_landed_cost(cost_row)  # completes sales_value calc
        outfile = tmp_path / "outfile.xlsx"

        with patch("src.adapters.startfile"):
            write_outfile({"sku-a": inv_row}, outfile_name=str(outfile))

        wb = openpyxl.load_workbook(outfile)
        header = [c.value for c in next(wb.active.iter_rows(max_row=1, max_col=30))]
        data_row = [
            c.value for c in next(wb.active.iter_rows(min_row=2, max_row=2, max_col=30))
        ]
        by_header = dict(zip(header, data_row, strict=False))

        assert by_header["Amazon Value"] == Decimal(10)  # 5 units * unit_cost 2
        assert by_header["eBay Value"] == 0
