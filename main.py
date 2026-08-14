from __future__ import annotations

import argparse

from src.adapters import (
    allocate_landed_costs,
    build_inventory,
    give_reader,
    give_transfer_reader,
    write_outfile,
)
from src.data import FailedRow, Header, InventoryRow, LandedCostRow
from src.inventory_kits.reader import ExcelKitReader

_FAILED_INVENTORY_ROWS: list[FailedRow] = []
_FAILED_PURCHASE_ROWS: list[FailedRow] = []
_FAILED_TRANSFER_ROWS: list[FailedRow] = []

_INV_HEADER = Header.inventory_row(
    sku=2, 
    base_sku=3, 
    inventory=30
)

_PURCHASE_HEADER = Header.landed_cost(
    sku=6, 
    qty=8, 
    unit_cost=20, 
    date=5
)

_TRANSFER_HEADER = Header.transfer_row(
    from_sku = 0,
    to_sku = 1,
    qty = 2,
    date = 3,
    date_format = "YYYY-MM-DD",
)


def calculate_all_lineitems_average_cost_from_excel(
    inventory_file_path: str,
    landed_cost_file_path: str,
    inventory_sheet_name: str,
    landed_cost_sheet_name: str,
    transfer_file_path: str,
    transfer_sheet_name: str,
):
    inv_reader = give_reader(
        file_path=inventory_file_path,
        sheet_name=inventory_sheet_name,
        header=_INV_HEADER,
        return_type=InventoryRow,
    )

    
    transfer_reader = give_transfer_reader(file_path = transfer_file_path, sheet_name = transfer_sheet_name, header = _TRANSFER_HEADER)

    cost_reader = give_reader(
        file_path=landed_cost_file_path,
        sheet_name=landed_cost_sheet_name,
        header=_PURCHASE_HEADER,
        return_type=LandedCostRow,
    )

    inventory, failed_inventory_rows = build_inventory(inv_reader)
    _FAILED_INVENTORY_ROWS.extend(failed_inventory_rows)

    transfers, failed_transfer_rows = build_transfers(transfer_reader)
    _FAILED_TRANSFER_ROWS.extend(failed_transfer_rows)

    failed_purchase_rows = allocate_landed_costs(cost_reader, inventory, transfers)
    _FAILED_PURCHASE_ROWS.extend(failed_purchase_rows)

    write_outfile(inventory)

    #TODO log failures instead of stdout
    for record in _FAILED_INVENTORY_ROWS:
        print(record.row, ", ", record.context)

    for record in _FAILED_PURCHASE_ROWS:
        print(record.row, ", ", record.context)


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

    parser.add_argument(
        "--inventory-file",
        "-i",
        default="private/inventory.xlsx"
    )

    parser.add_argument(
        "--transfer-file",
        "-t",
        default = "private/transfers.xlsx"
    )

    parser.add_argument(
        "--transfer-sheet-name",
        default = "Sheet1"
    )

    parser.add_argument(
        "--kit-upload",
        help=" Upload a kit file to split purchases and inventory into kit components.",
    )

    args = parser.parse_args()

    if args.kit_upload:
        kit_obj = ExcelKitReader(args.kit_upload)
        kit_obj.process_sellercloud_kit_export()
        kit_obj.close()

    calculate_all_lineitems_average_cost_from_excel(
        landed_cost_file_path=args.purchase_file,
        landed_cost_sheet_name=args.purchases_sheet_name,
        inventory_file_path=args.inventory_file,
        inventory_sheet_name=args.inventory_sheet_name,
        transfer_file_path = args.transfer_file,
        transfer_sheet_name = args.transfer_sheet_name,
    )


if __name__ == "__main__":
    main()
