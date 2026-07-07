from datetime import datetime as dt
from openpyxl import load_workbook
from typing import Generator

def main():
    cost_header = {
        'sku': 6,
        'qty': 8,
        'unit_cost': 12,
        'date': 7,
        'date_format': '%m-%d-%Y'
    }

    inventory_header = {
        'sku': 3,
        'inventory': 29
    }
    


class reader:
    def __init__(self, wb_path, ws_name):
        wb = load_workbook(filename = wb_path)
        self.ws = wb[ws_name]


        
        

    def readlineo(self) -> Generator[list[str]]:
        return self.ws.next






class LandedCostRow:
    def __init__(self, header: dict[str, int], row: list[str]):
        self.sku = row[header['sku']]
        self.qty = row[header['qty']]
        self.unit_cost = row[header['unit_cost']]
        self.date = dt.strftime(row[header['date']], header['date_format'])


class InventoryRow:
    def __init__(self, header: dict[str, int], row: list[str]):
        self.sku = row[header['sku']]
        self.inventory = row[header['inventory']]
        self.unallocated = self.inventory
        self.purchase_dates = []
        self.excluded_dates = []
        self.average_cost = None

    def allocate_from_landed_cost(self, cost_row: LandedCostRow):
        if self.inventory == 0:
            self.excluded_dates.append(cost_row.date)
            return
    
        elif cost_row.qty > self.unallocated:
            self.unit_cost += self.unallocated * cost_row.unit_cost
            self.purchase_dates.append(cost_row.date)

        else:
            self.unit_cost += self.allocated * cost_row.unit_cost
            self.purchase_dates.append(cost_row.date)



    
