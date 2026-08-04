from __future__ import annotations

from unittest.mock import patch

import pytest

from src.data import FailedRow
from src.main import calculate_all_lineitems_average_cost_from_excel, main


@pytest.fixture(autouse=True)
def _reset_failed_row_globals():
    import src.main as main_module

    main_module._FAILED_INVENTORY_ROWS.clear()
    main_module._FAILED_PURCHASE_ROWS.clear()
    yield
    main_module._FAILED_INVENTORY_ROWS.clear()
    main_module._FAILED_PURCHASE_ROWS.clear()


class TestCalculateAllLineitemsAverageCostFromExcel:
    def test_wires_readers_builds_inventory_allocates_costs_and_writes_outfile(self):
        inv_reader = object()
        cost_reader = object()
        inventory = {"sku-a": object()}

        with (
            patch(
                "src.main.give_reader", side_effect=[inv_reader, cost_reader]
            ) as mock_give_reader,
            patch(
                "src.main.build_inventory", return_value=(inventory, [])
            ) as mock_build_inventory,
            patch("src.main.allocate_landed_costs", return_value=[]) as mock_allocate,
            patch("src.main.write_outfile") as mock_write_outfile,
        ):
            calculate_all_lineitems_average_cost_from_excel(
                inventory_file_path="inv.xlsx",
                landed_cost_file_path="cost.xlsx",
                inventory_sheet_name="Inventory",
                landed_cost_sheet_name="Purchases",
            )

        assert mock_give_reader.call_count == 2
        mock_build_inventory.assert_called_once_with(inv_reader)
        mock_allocate.assert_called_once_with(cost_reader, inventory)
        mock_write_outfile.assert_called_once_with(inventory)

    def test_accumulates_failed_rows_into_module_level_lists(self):
        inv_fail = FailedRow(row=["bad-inv"], error=ValueError(), context="bad inventory row")
        cost_fail = FailedRow(row=["bad-cost"], error=ValueError(), context="bad cost row")

        with (
            patch("src.main.give_reader", side_effect=[object(), object()]),
            patch(
                "src.main.build_inventory",
                return_value=({"sku-a": object()}, [inv_fail]),
            ),
            patch("src.main.allocate_landed_costs", return_value=[cost_fail]),
            patch("src.main.write_outfile"),
        ):
            calculate_all_lineitems_average_cost_from_excel(
                inventory_file_path="inv.xlsx",
                landed_cost_file_path="cost.xlsx",
                inventory_sheet_name="Inventory",
                landed_cost_sheet_name="Purchases",
            )

        import src.main as main_module

        assert main_module._FAILED_INVENTORY_ROWS == [inv_fail]
        assert main_module._FAILED_PURCHASE_ROWS == [cost_fail]


class TestMainCli:
    def test_parses_args_and_delegates_to_calculation(self):
        argv = [
            "main.py",
            "--inventory-file",
            "inv.xlsx",
            "--purchase-file",
            "cost.xlsx",
        ]
        with (
            patch("sys.argv", argv),
            patch("src.main.calculate_all_lineitems_average_cost_from_excel") as mock_calc,
        ):
            main()

        mock_calc.assert_called_once_with(
            landed_cost_file_path="cost.xlsx",
            landed_cost_sheet_name="PURCHASES",
            inventory_file_path="inv.xlsx",
            inventory_sheet_name="Inventory",
        )

    def test_kit_upload_flag_processes_kit_file_before_calculation(self):
        argv = ["main.py", "--kit-upload", "kits.xlsx"]
        with (
            patch("sys.argv", argv),
            patch("src.main.ExcelKitReader") as mock_kit_reader_cls,
            patch("src.main.calculate_all_lineitems_average_cost_from_excel"),
        ):
            main()

        mock_kit_reader_cls.assert_called_once_with("kits.xlsx")
        instance = mock_kit_reader_cls.return_value
        instance.process_sellercloud_kit_export.assert_called_once()
        instance.close.assert_called_once()

    def test_no_kit_upload_flag_skips_kit_processing(self):
        argv = ["main.py"]
        with (
            patch("sys.argv", argv),
            patch("src.main.ExcelKitReader") as mock_kit_reader_cls,
            patch("src.main.calculate_all_lineitems_average_cost_from_excel"),
        ):
            main()

        mock_kit_reader_cls.assert_not_called()
