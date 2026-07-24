from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from collections.abc import Sequence
from collections import defaultdict
from datetime import datetime as dt
from decimal import Decimal
from typing import Any
from typing import Self

from typeguard import typechecked

from copy import copy


class RowLike(ABC):
    must_sort: bool = False
    header: dict[str, int]
    sku: str
    qty: Decimal

    @classmethod
    @abstractmethod
    def from_row(cls, row: Sequence[Any], header: Header) -> Self | None: ...

    def allocate_from_landed_cost(self, cost_row):
        raise NotImplementedError("Optional method.")


kit_ref: dict[str, dict[str, int]] = {}


def split_kits(func):
    def wrapper(*args, **kwargs):
        item: RowLike = func(*args, **kwargs)
        if item is None:
            return
        if not isinstance(item, RowLike):
            raise TypeError("Expected Rowlike, got %s", type(item))

        if item.sku not in kit_ref:
            yield item
            return
        
        for c_sku, c_qty in kit_ref[item.sku].items():
                c = copy(item)
                c.sku = c_sku
                c.qty = item.qty * c_qty # Multiply parent inventory level by kit component qty 
                yield c
    return wrapper

class LandedCostRow(RowLike):
    """
    A specific item purchase record with a sku, quantity, date and cost.
    """
    must_sort = True

    def __init__(self, row: LandedCostDTO) -> None:
        self.sku: str = row.sku
        self.qty: Decimal = row.qty
        self.unit_cost: Decimal = row.unit_cost
        self.date: dt = row.date

    def __repr__(self) -> str:
        return f"{self.sku},{self.qty},{self.unit_cost},{self.date})"

    
    @classmethod
    @split_kits
    def from_row(cls, row, header) -> LandedCostRow | None:
        dto = LandedCostDTO.sanitize(row, header)
        if not dto:
            return None
        row_like = cls(dto)
        return row_like

    @classmethod
    def sort_key(cls, row: LandedCostRow) -> Any:
        return row.date


class InventoryRow(RowLike):
    """
    An inventory item with quantity and allocated quantity. Has no time-awareness. 
    """
    must_sort = False

    def __init__(self, row: InventoryDTO) -> None:
        self.sku: str = row.sku
        self.qty: Decimal = row.inventory
        # Initialize unallocated to the current inventory level
        self.unallocated: Decimal = row.inventory

        self.purchase_dates: list[dt] = []
        self.excluded_dates: list[dt] = []
        self.total_cost: Decimal = Decimal(0)
        self.average_cost: Decimal | None = None

    @classmethod
    def from_row(cls, row, header: Header) -> InventoryRow | None:
        dto = InventoryDTO.sanitize(row, header)
        if dto is None:
            return None
        return cls(dto)

    def export(self) -> dict:
        return {
            "a": self.sku,
            "b": self.qty,
            "c": self.unallocated,
            # Maybe give choice for dt fmt in export? hardcoded for now
            "d": " | ".join(
                [dt.strftime(date, "%Y-%m-%d") for date in self.purchase_dates]
            ),
            "e": " | ".join(
                [dt.strftime(date, "%Y-%m-%d") for date in self.excluded_dates]
            ),
            "f": self.total_cost,
            "g": self.average_cost,
        }

    def allocate_from_landed_cost(self, cost_row: LandedCostRow):
        if self.unallocated == 0:
            self.excluded_dates.append(cost_row.date)
            return

        elif cost_row.qty >= self.unallocated:
            self.total_cost += self.unallocated * cost_row.unit_cost
            self.average_cost = self.total_cost / self.qty
            self.purchase_dates.append(cost_row.date)
            self.unallocated = Decimal(0)
            return

        else:
            self.total_cost += cost_row.qty * cost_row.unit_cost
            self.unallocated -= cost_row.qty
            self.average_cost = self.total_cost / self.unallocated
            self.purchase_dates.append(cost_row.date)

    def __repr__(self) -> str:
        return (
            f"InventoryRow(sku={self.sku!r}, "
            f"inventory={self.qty!r}, "
            f"average_cost={self.average_cost!r}, "
            f"purchase_dates={self.purchase_dates!r}, "
            f"excluded_dates={self.excluded_dates!r}, "
            f"total_cost={self.total_cost!r})"
        )


class Header:
    """ 
    Maps raw data to RowLike instance, used by RowLike.from_row class method. 
    Expected to be defined in Reader instance. 
    """
    sku: int
    base_sku: int
    qty: int
    inventory: int
    unit_cost: int
    date: int
    date_format: str

    @classmethod
    def landed_cost(
        cls,
        sku,
        qty,
        unit_cost,
        date,
        date_format="%Y-%m-%d",
    ) -> Header:
        """ Creates a Header instance with all necessary LandedCostRow mappings. """

        h = Header()
        h.sku = sku
        h.qty = qty
        h.unit_cost = unit_cost
        h.date = date
        h.date_format = date_format
        return h

    @classmethod
    def inventory_row(
        cls, 
        sku, 
        base_sku, 
        inventory
    ) -> Header:
        """ Creates a Header instance with all necessary InventoryRow mappings."""
        
        h = Header()
        h.sku = sku
        h.base_sku = base_sku
        h.inventory = inventory
        return h

    def __repr__(self):
        return f"Header({self.__dict__})"


@typechecked
class InventoryDTO:
    sku: str
    base_sku: str
    inventory: Decimal

    @typechecked
    @classmethod
    def sanitize(cls, row, header: Header) -> InventoryDTO | None:
        dto = InventoryDTO()
        try:
            sku = str(row[header.sku])
            base_sku = str(row[header.base_sku])
            inventory = Decimal(row[header.inventory])
        except ValueError:
            return None

        banned_char = [" "]

        if sku != base_sku:
            return None
        if len([c for c in banned_char if c in sku]) > 0:
            return None

        dto.sku = sku
        dto.base_sku = base_sku
        dto.inventory = inventory
        return dto


class LandedCostDTO:
    sku: str
    qty: Decimal
    unit_cost: Decimal
    date: dt

    @classmethod
    def sanitize(cls, row, header: Header) -> LandedCostDTO | None:
        dto = LandedCostDTO()
        try:
            sku = str(row[header.sku])
            qty = Decimal(row[header.qty])
            unit_cost = Decimal(row[header.unit_cost])
            date: dt | str = row[header.date]

        except ValueError, TypeError:
            return None

        dto.sku = sku
        dto.qty = qty
        dto.unit_cost = unit_cost

        if not date:
            return None

        if not isinstance(date, dt):
            try:
                date = dt.strptime(date, header.date_format)
            except ValueError:
                return None
        dto.date = date

        if not all(vars(dto)):
            return None
        return dto



