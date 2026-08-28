from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime

from src.adapters import (
    allocate_landed_costs,
    build_inventory,
    build_transfers,
    give_reader,
    give_transfer_reader,
    record_sales,
    write_outfile,
)
from src.data import FailedRow, Header, InventoryRow, LandedCostRow, SalesRow
from src.data.excel import TransactionSheetDateColumns, remove_wb_dates_after_target
from src.inventory_kits.reader import ExcelKitReader

formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("COGS")
logger.setLevel(0)


def setup_logging(handler_name, log_file=None, level=20):
    if not log_file:
        handler = logging.StreamHandler(sys.stdout)
    else:
        handler = logging.FileHandler(log_file)
    handler.setFormatter(formatter)
    handler.name = handler_name

    handler.setLevel(level)
    logger.addHandler(handler)
    return logger


_FAILED_INVENTORY_ROWS: list[FailedRow] = []
_FAILED_PURCHASE_ROWS: list[FailedRow] = []
_FAILED_TRANSFER_ROWS: list[FailedRow] = []
_FAILED_SALES_ROWS: list[FailedRow] = []

_INV_HEADER = Header.inventory_row(sku=2, base_sku=3, inventory=30)

_PURCHASE_HEADER = Header.landed_cost(sku=6, qty=8, unit_cost=20, date=5)

_TRANSFER_HEADER = Header.transfer_row(
    from_sku=0,
    to_sku=1,
    qty=2,
    date=3,
    date_format="%Y-%m-%d",
)

# Placeholder columns -- update to match the real sales sheet layout.
# One row per sku; each channel below maps to its own qty-sold column.
# Keys must match SalesData.sales_qty's keys exactly (case-sensitive).
_SALES_HEADER = Header.sales_row(
    sku=2,
    channel_columns={
        "Amazon": 21,
        "eBay": 17,
        "Etsy": 18,
        "Houzz": 19,
        "Shopify": 16,
        "Walmart": 24,
        "Wayfair": 20,
    },
)

_TRANSACTION_SHEET_DATE_COLUMNS: TransactionSheetDateColumns = {
    "Purchases": 4,
    "Prior Period Returns": 3,
    "Adjustments": 1,
    "AMAZON SC": 2,
    "EBAY": 43,
    "ETSY": 14,
    "HOUZZ": 2,
    "SHOPIFY": 15,
    "WALMART": 2,
    "WAYFAIR": 2,
    "Elegance_RCH": 5,
}


def calculate_all_lineitems_average_cost_from_excel(
    inventory_file_path: str,
    landed_cost_file_path: str,
    inventory_sheet_name: str,
    landed_cost_sheet_name: str,
    transfers={},
    as_of_date: datetime | None = None,
    sales_file_path: str | None = None,
    sales_sheet_name: str | None = None,
):
    if as_of_date:
        remove_wb_dates_after_target(
            inventory_file_path, as_of_date, _TRANSACTION_SHEET_DATE_COLUMNS
        )

    inv_reader = give_reader(
        file_path=inventory_file_path,
        sheet_name=inventory_sheet_name,
        header=_INV_HEADER,
        return_type=InventoryRow,
    )
    _PURCHASE_HEADER.as_of_date = as_of_date
    cost_reader = give_reader(
        file_path=landed_cost_file_path,
        sheet_name=landed_cost_sheet_name,
        header=_PURCHASE_HEADER,
        return_type=LandedCostRow,
    )

    inventory, failed_inventory_rows = build_inventory(inv_reader)
    _FAILED_INVENTORY_ROWS.extend(failed_inventory_rows)

    if sales_file_path and sales_sheet_name:
        sales_reader = give_reader(
            file_path=sales_file_path,
            sheet_name=sales_sheet_name,
            header=_SALES_HEADER,
            return_type=SalesRow,
        )
        failed_sales_rows = record_sales(sales_reader, inventory)
        _FAILED_SALES_ROWS.extend(failed_sales_rows)

    failed_purchase_rows = allocate_landed_costs(cost_reader, inventory, transfers)
    _FAILED_PURCHASE_ROWS.extend(failed_purchase_rows)

    write_outfile(inventory)

    # TODO log failures instead of stdout
    for record in _FAILED_INVENTORY_ROWS:
        logger.info(record.context, ", ", record.row)

    for record in _FAILED_PURCHASE_ROWS:
        logger.info(record.context, ", ", record.row)

    for record in _FAILED_TRANSFER_ROWS:
        logger.info(record.context, ", ", record.row)

    for record in _FAILED_SALES_ROWS:
        logger.info(record.row, ", ", record.context)


def _transfers(transfer_file_path, transfer_sheet_name):

    transfer_reader = give_transfer_reader(
        file_path=transfer_file_path,
        sheet_name=transfer_sheet_name,
        header=_TRANSFER_HEADER,
    )

    transfers, failed_transfer_rows = build_transfers(transfer_reader)
    _FAILED_TRANSFER_ROWS.extend(failed_transfer_rows)

    return transfers, failed_transfer_rows


def _parse_as_of_date(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a valid date, expected format YYYY-MM-DD"
        ) from e


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Average cost, Inventory Asset Valuation"
    )

    parser.add_argument(
        "--inventory-sheet-name",
        help='Inventory file sheetname to be used in inventory calculation, defaults to "Inventory ". ',
        default="Inventory",
    )

    parser.add_argument(
        "--purchases-sheet-name",
        help='purchases file sheetname to be provide purchase history, defaults to "Purchases".',
        default="PURCHASES",
    )

    parser.add_argument(
        "--purchase-file",
        "-p",
        default="private/landed cost.xlsx",
    )

    parser.add_argument("--inventory-file", "-i", default="private/inventory.xlsx")

    parser.add_argument("--transfer-file", "-t")

    parser.add_argument("--transfer-sheet-name")

    parser.add_argument("--sales-file")

    parser.add_argument("--sales-sheet-name")

    parser.add_argument(
        "--kit-upload",
        help=" Upload a kit file to split purchases and inventory into kit components.",
    )

    parser.add_argument(
        "--as-of-date",
        type=_parse_as_of_date,
        default=None,
        help="fmt: [YYYY-MM-DD] remove inventory transactions that postdate --as-of-date,",
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose")

    parser.add_argument(
        "--very-verbose", "-vv", action="store_true", help="More runtime info"
    )

    args = parser.parse_args()

    if args.verbose:
        setup_logging(handler_name="verbose", level=20)
    if args.very_verbose:
        # Very verbose overrides verbose handler if it exists.
        for handler in logging.getLogger().handlers:
            if handler.name == "verbose":
                handler.close()

        setup_logging(handler_name="very_verbose", level=10)

    if args.kit_upload:
        kit_obj = ExcelKitReader(args.kit_upload)
        kit_obj.process_sellercloud_kit_export()
        kit_obj.close()

    if args.transfer_file and args.transfer_sheet_name:
        transfers, _ = _transfers(
            transfer_file_path=args.transfer_file,
            transfer_sheet_name=args.transfer_sheet_name,
        )
    else:
        transfers = {}

    calculate_all_lineitems_average_cost_from_excel(
        landed_cost_file_path=args.purchase_file,
        landed_cost_sheet_name=args.purchases_sheet_name,
        inventory_file_path=args.inventory_file,
        inventory_sheet_name=args.inventory_sheet_name,
        transfers=transfers,
        as_of_date=args.as_of_date,
        sales_file_path=args.sales_file,
        sales_sheet_name=args.sales_sheet_name,
    )


if __name__ == "__main__":
    main()
