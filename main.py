from datetime import datetime as dt
import openpyxl as xl

from data.datarows import InventoryRow, LandedCostRow
from data.reader import Reader

from sys import getrefcount

def main():
    inv_reader = Reader('alt_inv_source.xlsx', 'Sheet1', InventoryRow)
    cost_reader = Reader('landed cost.xlsx', 'PURCHASES', LandedCostRow)
    mrd = dt.max
    inventory: dict[str, InventoryRow] = {}

    for inv_row in inv_reader.readlineo():
        inventory[inv_row.sku] = inv_row

    for cost_row in cost_reader.readlineo():
        if cost_row.date > mrd:
            raise ValueError('Landed Cost field is not sorted Newest to Oldest')
        mrd = cost_row.date
        if not cost_row.sku in inventory:
            continue
        inventory[cost_row.sku].allocate_from_landed_cost(cost_row)
    

    #write outfile
    wb = xl.Workbook()
    ws = wb.active
    if not ws:
        raise ValueError
    ws.title = "Inventory Asset Value"
    ws.append(["Sku", "total Cost", "Average Cost", "Inventory"])

    print(inventory['CH-S56-11S-AB'], inventory['CH-S56-11S-AB'].inventory, inventory['CH-S56-11S-AB'].unallocated)

    # for item in inventory.values():
    #     ws.append(item.export())

    # wb.save('outfile.xlsx')

if __name__ == "__main__":
    main()

    