from abc import ABC, abstractmethod
from typing import Self

from datetime import datetime as dt

class RowLike(ABC):
    def __init__(self, row: list[str]):
        self.sku: str

    @classmethod
    @abstractmethod
    def from_row(cls, row) -> Self|None:
        row_like = cls(row)
        return row_like
    
    def allocate_from_landed_cost(self, cost_row):
        raise NotImplementedError("This is an optional method that is not valid for all types of RowLike")
    

class LandedCostRow(RowLike):
    header = {
    'sku': 6,
    'qty': 10,
    'unit_cost': 20,
    'date': 5,
    'date_format': '%m-%d-%Y'
}
    
    def __init__(self, row: list[str]):
        
        self.sku = row[self.header['sku']]
        self.qty = int(row[self.header['qty']])
        self.unit_cost = float(row[self.header['unit_cost']])
        self.date = dt.strptime(row[self.header['date']], self.header['date_format']) if not isinstance(row[self.header['date']], dt) else row[self.header['date']]

    def __repr__(self) -> str:
        return f"LandedCostRow(sku={self.sku}, qty={self.qty}, unit_cost={self.unit_cost}, date={self.date})"

    @classmethod
    def from_row(cls, row) -> LandedCostRow|None:
        if not row[cls.header['date']] or not row[cls.header['unit_cost']]:
            return None
        row_like = cls(row)
        return row_like


class InventoryRow(RowLike):
    header = {
            'sku': 1,
            'base_sku': 0,
            'inventory': 2
        }
    user_defined = {
        38: 'z-Non-Inventory Item',
        4: 'zzDummy',
        5: 'zzDummy Placeholder'
    }
    
    def __init__(self, row: list[str]):
        try:
        
            self.sku = row[self.header['sku']]
            self.inventory = int(float(row[self.header['inventory']]))
            self.unallocated = self.inventory
            self.purchase_dates = []
            self.excluded_dates = []
            self.total_cost = 0
            self.average_cost = None
        except Exception as e:
            raise Exception(f"{[(i, val) for i, val in enumerate(row)]} has invalid data") from e

    def __repr__(self) -> str:
        return f"InventoryRow(sku={self.sku}, inventory={self.inventory}, average_cost={self.average_cost}, purchase_dates={self.purchase_dates}, excluded_dates={self.excluded_dates}, total_cost={self.total_cost})"

    @classmethod
    def from_row(cls, row) -> RowLike|None:
        if (    
            not (row[cls.header['sku']])
            # or (row[cls.header['sku']] != row[cls.header['base_sku']])
            # or (" " in str(row[cls.header['sku']]))
            # or (any(row[col_num] == exclusion_val for col_num, exclusion_val in cls.user_defined.items()))
        ):
            print(f"{row[cls.header['base_sku']]} rejected")
            return None
        
        return cls(row)

    def allocate_from_landed_cost(self, cost_row: LandedCostRow):
        if self.unallocated == 0:
            self.excluded_dates.append(cost_row.date)
            return
    
        elif cost_row.qty >= self.unallocated:
            self.total_cost += self.unallocated * cost_row.unit_cost
            self.average_cost = self.total_cost / self.inventory
            self.purchase_dates.append(cost_row.date)
            self.unallocated = 0
            return

        else:
            self.total_cost += (cost_row.qty * cost_row.unit_cost)
            self.unallocated -= cost_row.qty
            self.average_cost = self.total_cost / self.unallocated
            self.purchase_dates.append(cost_row.date)

