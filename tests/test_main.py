from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from main import _transfers, calculate_all_lineitems_average_cost_from_excel, main
from src.data import FailedRow


@pytest.fixture(autouse=True)
def _reset_failed_row_globals():
    import main as main_module

    main_module._FAILED_INVENTORY_ROWS.clear()
    main_module._FAILED_PURCHASE_ROWS.clear()
    main_module._FAILED_TRANSFER_ROWS.clear()
    main_module._FAILED_SALES_ROWS.clear()
    yield
    main_module._FAILED_INVENTORY_ROWS.clear()
    main_module._FAILED_PURCHASE_ROWS.clear()
    main_module._FAILED_TRANSFER_ROWS.clear()
    main_module._FAILED_SALES_ROWS.clear()


class TestCalculateAllLineitemsAverageCostFromExcel:
    def test_wires_readers_builds_inventory_allocates_costs_and_writes_outfile(self):
        inv_reader = object()
        cost_reader = object()
        inventory = {"sku-a": object()}

        with (
            patch(
                "main.give_reader", side_effect=[inv_reader, cost_reader]
            ) as mock_give_reader,
            patch(
                "main.build_inventory", return_value=(inventory, [])
            ) as mock_build_inventory,
            patch("main.allocate_landed_costs", return_value=[]) as mock_allocate,
            patch("main.write_outfile") as mock_write_outfile,
        ):
            calculate_all_lineitems_average_cost_from_excel(
                inventory_file_path="inv.xlsx",
                landed_cost_file_path="cost.xlsx",
                inventory_sheet_name="Inventory",
                landed_cost_sheet_name="Purchases",
            )

        transfers = {}

        assert mock_give_reader.call_count == 2
        mock_build_inventory.assert_called_once_with(inv_reader)
        mock_allocate.assert_called_once_with(cost_reader, inventory, transfers)
        mock_write_outfile.assert_called_once_with(inventory)

    def test_records_sales_against_inventory_before_allocating_landed_costs(self):
        inv_reader = object()
        cost_reader = object()
        sales_reader = object()
        inventory = {"sku-a": object()}
        call_order = []

        def _record_sales(reader, inv):
            call_order.append("record_sales")
            assert reader is sales_reader
            assert inv is inventory
            return []

        def _allocate(reader, inv, transfers):
            call_order.append("allocate_landed_costs")
            return []

        with (
            patch(
                "main.give_reader",
                side_effect=[inv_reader, cost_reader, sales_reader],
            ) as mock_give_reader,
            patch("main.build_inventory", return_value=(inventory, [])),
            patch("main.record_sales", side_effect=_record_sales) as mock_record,
            patch("main.allocate_landed_costs", side_effect=_allocate),
            patch("main.write_outfile"),
        ):
            calculate_all_lineitems_average_cost_from_excel(
                inventory_file_path="inv.xlsx",
                landed_cost_file_path="cost.xlsx",
                inventory_sheet_name="Inventory",
                landed_cost_sheet_name="Purchases",
                sales_file_path="sales.xlsx",
                sales_sheet_name="Sales",
            )

        assert mock_give_reader.call_count == 3
        mock_record.assert_called_once_with(sales_reader, inventory)
        assert call_order == ["record_sales", "allocate_landed_costs"]

    def test_skips_sales_reading_when_sales_file_or_sheet_not_given(self):
        with (
            patch(
                "main.give_reader", side_effect=[object(), object()]
            ) as mock_give_reader,
            patch("main.build_inventory", return_value=({"sku-a": object()}, [])),
            patch("main.record_sales") as mock_record,
            patch("main.allocate_landed_costs", return_value=[]),
            patch("main.write_outfile"),
        ):
            calculate_all_lineitems_average_cost_from_excel(
                inventory_file_path="inv.xlsx",
                landed_cost_file_path="cost.xlsx",
                inventory_sheet_name="Inventory",
                landed_cost_sheet_name="Purchases",
            )

        assert mock_give_reader.call_count == 2
        mock_record.assert_not_called()

    def test_accumulates_failed_sales_rows_into_module_level_list(self):
        import main as main_module

        sales_fail = FailedRow(
            row=["bad-sale"], error=ValueError(), context="bad sale row"
        )

        with (
            patch("main.give_reader", side_effect=[object(), object(), object()]),
            patch("main.build_inventory", return_value=({"sku-a": object()}, [])),
            patch("main.record_sales", return_value=[sales_fail]),
            patch("main.allocate_landed_costs", return_value=[]),
            patch("main.write_outfile"),
        ):
            calculate_all_lineitems_average_cost_from_excel(
                inventory_file_path="inv.xlsx",
                landed_cost_file_path="cost.xlsx",
                inventory_sheet_name="Inventory",
                landed_cost_sheet_name="Purchases",
                sales_file_path="sales.xlsx",
                sales_sheet_name="Sales",
            )

        assert main_module._FAILED_SALES_ROWS == [sales_fail]

    def test_accumulates_failed_rows_into_module_level_lists(self):
        inv_fail = FailedRow(
            row=["bad-inv"], error=ValueError(), context="bad inventory row"
        )
        cost_fail = FailedRow(
            row=["bad-cost"], error=ValueError(), context="bad cost row"
        )

        with (
            patch("main.give_reader", side_effect=[object(), object()]),
            patch(
                "main.build_inventory",
                return_value=({"sku-a": object()}, [inv_fail]),
            ),
            patch("main.allocate_landed_costs", return_value=[cost_fail]),
            patch("main.write_outfile"),
        ):
            calculate_all_lineitems_average_cost_from_excel(
                inventory_file_path="inv.xlsx",
                landed_cost_file_path="cost.xlsx",
                inventory_sheet_name="Inventory",
                landed_cost_sheet_name="Purchases",
            )

        import main as main_module

        assert main_module._FAILED_INVENTORY_ROWS == [inv_fail]
        assert main_module._FAILED_PURCHASE_ROWS == [cost_fail]

    def _DEACTIVATED_prints_failed_transfer_rows_collected_before_this_call(
        self, capsys
    ):
        # _FAILED_TRANSFER_ROWS is populated by _transfers() before this
        # function runs (transfers are read before the purchase workbook),
        # so this only exercises the print loop reading that module-level
        # list, not the population itself.
        import main as main_module

        transfer_fail = FailedRow(
            row=["bad-transfer"], error=ValueError(), context="bad transfer row"
        )
        main_module._FAILED_TRANSFER_ROWS.append(transfer_fail)

        with (
            patch("main.give_reader", side_effect=[object(), object()]),
            patch("main.build_inventory", return_value=({"sku-a": object()}, [])),
            patch("main.allocate_landed_costs", return_value=[]),
            patch("main.write_outfile"),
        ):
            calculate_all_lineitems_average_cost_from_excel(
                inventory_file_path="inv.xlsx",
                landed_cost_file_path="cost.xlsx",
                inventory_sheet_name="Inventory",
                landed_cost_sheet_name="Purchases",
            )

        assert "bad transfer row" in capsys.readouterr().out

    def test_as_of_date_prunes_inventory_workbook_before_reading_it(self):
        import main as main_module

        as_of = datetime(2024, 6, 1, tzinfo=UTC)
        pruned = []

        def fake_prune(wb_path, target, transaction_sheets):
            pruned.append((wb_path, target, transaction_sheets))

        def fake_give_reader(file_path, sheet_name, header, return_type):
            if file_path == "inv.xlsx":
                assert pruned, "inventory workbook must be pruned before it is read"
            return object()

        with (
            patch(
                "main.remove_wb_dates_after_target", side_effect=fake_prune
            ) as mock_prune,
            patch("main.give_reader", side_effect=fake_give_reader),
            patch("main.build_inventory", return_value=({"sku-a": object()}, [])),
            patch("main.allocate_landed_costs", return_value=[]),
            patch("main.write_outfile"),
        ):
            calculate_all_lineitems_average_cost_from_excel(
                inventory_file_path="inv.xlsx",
                landed_cost_file_path="cost.xlsx",
                inventory_sheet_name="Inventory",
                landed_cost_sheet_name="Purchases",
                as_of_date=as_of,
            )

        mock_prune.assert_called_once_with(
            "inv.xlsx", as_of, main_module._TRANSACTION_SHEET_DATE_COLUMNS
        )

    def test_as_of_date_is_set_on_purchase_header_for_cost_row_filtering(self):
        import main as main_module

        as_of = datetime(2024, 6, 1, tzinfo=UTC)

        with (
            patch("main.remove_wb_dates_after_target"),
            patch("main.give_reader", side_effect=[object(), object()]),
            patch("main.build_inventory", return_value=({"sku-a": object()}, [])),
            patch("main.allocate_landed_costs", return_value=[]),
            patch("main.write_outfile"),
        ):
            calculate_all_lineitems_average_cost_from_excel(
                inventory_file_path="inv.xlsx",
                landed_cost_file_path="cost.xlsx",
                inventory_sheet_name="Inventory",
                landed_cost_sheet_name="Purchases",
                as_of_date=as_of,
            )

        assert main_module._PURCHASE_HEADER.as_of_date == as_of

    def test_no_as_of_date_skips_pruning(self):
        with (
            patch("main.remove_wb_dates_after_target") as mock_prune,
            patch("main.give_reader", side_effect=[object(), object()]),
            patch("main.build_inventory", return_value=({"sku-a": object()}, [])),
            patch("main.allocate_landed_costs", return_value=[]),
            patch("main.write_outfile"),
        ):
            calculate_all_lineitems_average_cost_from_excel(
                inventory_file_path="inv.xlsx",
                landed_cost_file_path="cost.xlsx",
                inventory_sheet_name="Inventory",
                landed_cost_sheet_name="Purchases",
            )

        mock_prune.assert_not_called()


class TestTransfersHelper:
    def test_returns_the_transfers_dict_and_failed_rows_as_a_tuple(self):
        transfers_dict = {"sku-a": object()}
        failed = [FailedRow(row=["bad"], error=ValueError(), context="bad row")]

        with (
            patch("main.give_transfer_reader", return_value=object()),
            patch("main.build_transfers", return_value=(transfers_dict, failed)),
        ):
            result = _transfers(
                transfer_file_path="transfers.xlsx",
                transfer_sheet_name="Transfers",
            )

        assert result == (transfers_dict, failed)

    def test_extends_the_module_level_failed_transfer_rows(self):
        import main as main_module

        failed = [FailedRow(row=["bad"], error=ValueError(), context="bad row")]

        with (
            patch("main.give_transfer_reader", return_value=object()),
            patch("main.build_transfers", return_value=({}, failed)),
        ):
            _transfers(
                transfer_file_path="transfers.xlsx",
                transfer_sheet_name="Transfers",
            )

        assert main_module._FAILED_TRANSFER_ROWS == failed


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
            patch("main.calculate_all_lineitems_average_cost_from_excel") as mock_calc,
        ):
            main()

        transfers = {}

        mock_calc.assert_called_once_with(
            landed_cost_file_path="cost.xlsx",
            landed_cost_sheet_name="PURCHASES",
            inventory_file_path="inv.xlsx",
            inventory_sheet_name="Inventory",
            transfers=transfers,
            as_of_date=None,
            sales_file_path=None,
            sales_sheet_name=None,
        )

    def test_sales_flags_are_passed_through_to_the_calculation(self):
        argv = [
            "main.py",
            "--inventory-file",
            "inv.xlsx",
            "--purchase-file",
            "cost.xlsx",
            "--sales-file",
            "sales.xlsx",
            "--sales-sheet-name",
            "Sales",
        ]
        with (
            patch("sys.argv", argv),
            patch("main.calculate_all_lineitems_average_cost_from_excel") as mock_calc,
        ):
            main()

        _, kwargs = mock_calc.call_args
        assert kwargs["sales_file_path"] == "sales.xlsx"
        assert kwargs["sales_sheet_name"] == "Sales"

    def test_transfer_flags_pass_the_transfers_dict_not_the_raw_tuple(self):
        # Regression test: main() used to do `transfers = _transfers(...)`
        # without unpacking -- _transfers() returns (dict, failed_rows), so
        # `transfers` ended up bound to that whole tuple. `sku in transfers`
        # against a (dict, list) 2-tuple is never true, so the entire
        # transfer-redirect feature silently never engaged.
        argv = [
            "main.py",
            "--inventory-file",
            "inv.xlsx",
            "--purchase-file",
            "cost.xlsx",
            "--transfer-file",
            "transfers.xlsx",
            "--transfer-sheet-name",
            "Transfers",
        ]
        transfers_dict = {"sku-a": object()}
        with (
            patch("sys.argv", argv),
            patch(
                "main._transfers", return_value=(transfers_dict, [])
            ) as mock_transfers,
            patch("main.calculate_all_lineitems_average_cost_from_excel") as mock_calc,
        ):
            main()

        mock_transfers.assert_called_once_with(
            transfer_file_path="transfers.xlsx",
            transfer_sheet_name="Transfers",
        )
        _, kwargs = mock_calc.call_args
        assert kwargs["transfers"] is transfers_dict

    def test_as_of_date_flag_parsed_and_passed_through(self):
        argv = [
            "main.py",
            "--inventory-file",
            "inv.xlsx",
            "--purchase-file",
            "cost.xlsx",
            "--as-of-date",
            "2024-06-01",
        ]
        with (
            patch("sys.argv", argv),
            patch("main.calculate_all_lineitems_average_cost_from_excel") as mock_calc,
        ):
            main()

        _, kwargs = mock_calc.call_args
        assert kwargs["as_of_date"] == datetime(2024, 6, 1, tzinfo=UTC)

    def test_invalid_as_of_date_format_exits_with_error(self):
        argv = ["main.py", "--as-of-date", "not-a-date"]
        with patch("sys.argv", argv), pytest.raises(SystemExit):
            main()

    def test_kit_upload_flag_processes_kit_file_before_calculation(self):
        argv = ["main.py", "--kit-upload", "kits.xlsx"]
        with (
            patch("sys.argv", argv),
            patch("main.ExcelKitReader") as mock_kit_reader_cls,
            patch("main.calculate_all_lineitems_average_cost_from_excel"),
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
            patch("main.ExcelKitReader") as mock_kit_reader_cls,
            patch("main.calculate_all_lineitems_average_cost_from_excel"),
        ):
            main()

        mock_kit_reader_cls.assert_not_called()
