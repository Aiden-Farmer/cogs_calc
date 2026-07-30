from __future__ import annotations

from os import startfile

import openpyxl as xl
import argparse

from data import excel
from data import Header
from data import InventoryRow
from data import LandedCostRow

from inventory_kits.reader import DataSourceError


def calculate_all_lineitems_average_cost_from_excel(
    inventory_file_path: str,
    landed_cost_filepath: str,
    inventory_sheet_name: str,
    landed_cost_sheet_name: str,
):

    if not inventory_file_path.endswith(".xlsx"):
        raise TypeError(
            "Inventory file must be \
                        .xlsx file type."
        )
    if not landed_cost_filepath.endswith("xlsx"):
        raise TypeError(
            "Landed cost file must be \
                        .xlsx file type."
        )

    inv_ds = excel.Source(inventory_file_path, inventory_sheet_name)

    lc_ds = excel.Source(landed_cost_filepath, landed_cost_sheet_name)

    inv_h = Header.inventory_row(
        sku=2,
        base_sku=3,
        inventory=30,
    )

    lc_h = Header.landed_cost(
        sku=6,
        qty=8,
        unit_cost=20,
        date=5,
    )

    inv_reader = excel.Reader(inv_ds, inv_h, InventoryRow)
    cost_reader = excel.Reader(lc_ds, lc_h, LandedCostRow)

    inventory: dict[str, InventoryRow] = {}

    for inv_row in inv_reader.readline():
        inventory[inv_row.sku] = inv_row
        print(inv_row)

    if not inventory:
        raise DataSourceError

    for cost_row in cost_reader.readline():
        if cost_row.sku not in inventory:
            continue
        inventory[cost_row.sku].allocate_from_landed_cost(cost_row)

    # write outfile
    wb = xl.Workbook()
    ws = wb.active
    if not ws:
        raise ValueError
    ws.title = "Inventory Asset Value"
    ws.append(
        [
            "SKU",
            "Inventory Cost",
            "Unallocated",
            "Dates Received",
            "Dates received not counting against Average Cost",
            "Total Cost",
            "Average Cost",
        ]
    )
    for item in inventory.values():
        ws.append(item.export())

    wb.save("outfile.xlsx")
    startfile("outfile.xlsx")


if __name__ == "__main__":
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
        nargs=1,
        default="private/landed cost.xlsx",
    )

    parser.add_argument(
        "--inventory-file", "-i", nargs=1, default="private/inventory.xlsx"
    )

    args = parser.parse_args()
    args._get_args()
    calculate_all_lineitems_average_cost_from_excel(
        landed_cost_filepath=args.purchase_file,
        landed_cost_sheet_name=args.purchases_sheet_name,
        inventory_file_path=args.inventory_file,
        inventory_sheet_name=args.inventory_sheet_name,
    )
