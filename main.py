from __future__ import annotations

from os import startfile

import openpyxl as xl

from data import excel
from data import Header
from data import InventoryRow
from data import LandedCostRow


def main():
    inv_ds = excel.Source("alt_inv_source.xlsx", "Sheet1")
    lc_ds = excel.Source("landed cost.xlsx", "PURCHASES")

    inv_h = Header.inventory_row(
        sku=1,
        base_sku=0,
        inventory=2,
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
    main()
