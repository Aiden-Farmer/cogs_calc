from datetime import datetime as dt
import openpyxl as xl
from os import startfile

from data.datarows import InventoryRow, LandedCostRow
from data.reader import ExcelFileReader, ExcelDataSource


from sys import getrefcount

def main():
    inv_ds = ExcelDataSource('alt_inv_source.xlsx', 'Sheet1')
    lc_ds = ExcelDataSource('landed cost.xlsx', 'PURCHASES')

    inv_reader = ExcelFileReader(inv_ds, InventoryRow)
    cost_reader = ExcelFileReader(lc_ds, LandedCostRow)
    inventory: dict[str, InventoryRow] = {}

    for inv_row in inv_reader.readlineo():
        inventory[inv_row.sku] = inv_row

    for cost_row in cost_reader.readlineo():
        if not cost_row.sku in inventory:
            continue
        inventory[cost_row.sku].allocate_from_landed_cost(cost_row)
    

    #write outfile
    wb = xl.Workbook()
    ws = wb.active
    if not ws:
        raise ValueError
    ws.title = "Inventory Asset Value"
    ws.append(["SKU", "Inventory Cost", "Unallocated", "Dates Received", "Dates received not counting against Average Cost", "Total Cost", "Average Cost"])
    for item in inventory.values():
        ws.append(item.export())

    wb.save('outfile.xlsx')
    startfile('outfile.xlsx')

if __name__ == "__main__":
    main()

    