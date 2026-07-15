from abc import ABC, abstractmethod
from typeguard import typechecked
from typing import Self, Any

from typeguard import TypeCheckError

from datetime import datetime as dt
from decimal import Decimal

class RowLike(ABC):
    must_sort: bool = False
    header: dict[str, int]
    sku: str

    @classmethod
    @abstractmethod
    def from_row(cls, row, header: Header,) -> Self|None:
        ...
    
    def allocate_from_landed_cost(self, cost_row):
        raise NotImplementedError("This is an optional method that is not valid for all types of RowLike")
    

class LandedCostRow(RowLike):
    must_sort = True
    
    def __init__(self, row: LandedCostDTO) -> None:
        self.sku: str           = row.sku
        self.qty: int           = row.qty
        self.unit_cost: Decimal = row.unit_cost
        self.date: dt           = row.date

    def __repr__(self) -> str:
        return f"LandedCostRow(sku={self.sku}, qty={self.qty}, unit_cost={self.unit_cost}, date={self.date})"

    @classmethod
    def from_row(cls, row, header) -> LandedCostRow|None:
        dto = LandedCostDTO.sanitize_to_dto(row, header)
        if not dto:
            return None
        row_like = cls(dto)
        return row_like

    @classmethod
    def sort_key(cls, row: "LandedCostRow") -> Any:
        return row.date

@typechecked
class InventoryRow(RowLike):
    must_sort = False
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
    date_format = '%Y-%m-%d'
    
    @typechecked
    def __init__(self, row: list[str]):
        self.sku: str                   = row[self.header['sku']]
        try:
            self.inventory: int         = int(float(row[self.header['inventory']]))
        except ValueError as e:
            raise TypeCheckError("Inventory Value must be int-like str") from e

        self.unallocated: int           = self.inventory
        self.purchase_dates: list[dt]   = []
        self.excluded_dates: list[dt]   = []
        self.total_cost: Decimal        = Decimal(0)
        self.average_cost: Decimal|None = None

    @classmethod
    def from_row(cls, row, header ) -> InventoryRow:
        if (    
            not (row[cls.header['sku']])
            or (row[cls.header['sku']] != row[cls.header['base_sku']])
        #     # or (" " in str(row[cls.header['sku']]))
        #     # or (any(row[col_num] == exclusion_val for col_num, exclusion_val in cls.user_defined.items()))
        ):
        #     print(f"{row[cls.header['base_sku']]} rejected")
            raise TypeCheckError('sku is either None or not == to base_sku')


        return cls(row)
    
    def export(self) -> dict:
        return {
            'a': self.sku,
            'b': self.inventory,
            'c': self.unallocated,
            'd': " | ".join([dt.strftime(date, self.date_format) for date in self.purchase_dates]),
            'e': " | ".join([dt.strftime(date, self.date_format) for date in self.excluded_dates]),
            'f': self.total_cost,
            'g': self.average_cost
            }

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

    def __repr__(self) -> str:
        return f"InventoryRow(sku={self.sku}, inventory={self.inventory}, average_cost={self.average_cost}, purchase_dates={self.purchase_dates}, excluded_dates={self.excluded_dates}, total_cost={self.total_cost})"


class Header:
    sku: int
    base_sku: int
    qty: int
    inventory: int
    unit_cost: int
    date: int
    date_format: str

    @classmethod
    def landed_cost(cls, sku, qty, unit_cost, date, date_format="") -> Header:
        h = Header()
        h.sku = sku
        h.qty = qty
        h.unit_cost = unit_cost
        h.date = date
        h.date_format = date_format
        return h

    @classmethod
    def inventory_row(cls, sku, base_sku, inventory) -> Header:
        h = Header()
        h.sku = sku
        h.base_sku = base_sku
        h.inventory = inventory
        return h

@typechecked
class InventoryDTO:
    #Test both DTOs for rejection logic/type safety. 
    pass

@typechecked
class LandedCostDTO:
    sku: str
    qty: int
    unit_cost: Decimal
    date: dt

    @classmethod
    def sanitize_to_dto(cls, row, header: Header) -> LandedCostDTO:
        dto = LandedCostDTO()
        dto.sku = row[header.sku]
        dto.qty = row[header.qty]
        dto.unit_cost = row[header.unit_cost]
        date = row[header.date]
        if not isinstance(date, dt):
            date = dt.strptime(date, header.date_format)
        dto.date = date
        return dto
