from datetime import date as dt
from openpyxl import load_workbook
from typing import Iterator
from abc import ABC, abstractmethod

class RowLike(ABC):
    def __init__(self, row: list[str]):
        self.sku = row[0]

    @classmethod
    @abstractmethod
    def from_row(cls, row) -> RowLike|None:
        row_like = cls(row)
        return row_like
    
    def allocate_from_landed_cost(self, cost_row):
        raise NotImplementedError("This is an optional method that is not valdi for all types of RowLike")
    

class Reader:
    def __init__(self, wb_path, ws_name, return_type: type[RowLike]):
        wb = load_workbook(filename = wb_path)
        self.ws = wb[ws_name]
        self.rt = return_type

    def readlineo(self) -> Iterator[RowLike]:
        for raw in self.ws.iter_rows(values_only=True):
            if (row := self.rt.from_row(raw)):
                yield row 

  


class LandedCostRow(RowLike):
    def __init__(self, row: list[str]):

        header = {
            'sku': 6,
            'qty': 8,
            'unit_cost': 12,
            'date': 7,
            'date_format': '%m-%d-%Y'
        }

        self.sku = row[header['sku']]
        self.qty = row[header['qty']]
        self.unit_cost = row[header['unit_cost']]
        self.date = dt.strptime(row[header['date']], header['date_format']) if not isinstance(row[header['date']], dt) else row[header['date']]

    @classmethod
    def from_row(cls, row) -> RowLike|None:
        return super().from_row(row)


class InventoryRow(RowLike):
    def __init__(self, row: list[str]):
        header = {
            'sku': 3,
            'base_sku': 2,
            'inventory': 29
        }
        
        self.sku = row[header['sku']]
        self.base_sku = row[header['base_sku']]
        self.inventory = row[header['inventory']]
        self.unallocated = self.inventory
        self.purchase_dates = []
        self.excluded_dates = []
        self.total_cost = 0
        self.average_cost = None

    def __repr__(self) -> str:
        return f"InventoryRow(sku={self.sku}, inventory={self.inventory}, average_cost={self.average_cost})"

    @classmethod
    def from_row(cls, row) -> RowLike|None:
        inv_row = cls(row)
        if inv_row.sku != inv_row.base_sku:
            return None
        return inv_row

    def allocate_from_landed_cost(self, cost_row):
        if self.unallocated == 0:
            self.excluded_dates.append(cost_row.date)
            return
        
        if self.inventory == 0:
            self.excluded_dates.append(cost_row.date)
            return
    
        elif cost_row.qty >= self.unallocated:
            self.total_cost += self.unallocated * cost_row.unit_cost
            self.average_cost = self.total_cost / self.inventory
            self.purchase_dates.append(cost_row.date)
            self.unallocated = 0

        else:
            self.total_cost += (cost_row.qty * cost_row.unit_cost)
            self.unallocated -= cost_row.qty
            self.purchase_dates.append(cost_row.date)



def main():
    
    inv_reader = Reader('inventory.xlsx', 'Inventory', InventoryRow)
    cost_reader = Reader('landed cost.xlsx', 'PURCHASES', LandedCostRow)
    mrd = dt.min
    inventory: dict[str, RowLike|InventoryRow] = {}

    for inv_row in inv_reader.readlineo():
        inventory[inv_row.sku] = inv_row

    for cost_row in cost_reader.readlineo():
        if cost_row.date < mrd:
            raise ValueError('Landed Cost fiel is not sorted Newest to Oldest')
        mrd = cost_row.date
        if cost_row.sku in inventory:
            inventory[cost_row.sku].allocate_from_landed_cost(cost_row)


    print(inventory)


if __name__ == "__main__":
    main()

    