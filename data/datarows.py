from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime as dt
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import Any, Self

from typeguard import typechecked

_INVALID_SKU_CHAR = {
    " ",
}


class RowLike(ABC):
    must_sort: bool = False
    header: dict[str, int]
    sku: str
    qty: Decimal

    @classmethod
    @abstractmethod
    def from_row(cls, row: Sequence[Any], header: Header) -> Self | FailedRow: ...


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
    def from_row(cls, row, header) -> LandedCostRow | FailedRow:
        dto = LandedCostDTO.sanitize(row, header)
        if isinstance(dto, FailedRow):
            return dto

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

    @typechecked
    @classmethod
    def from_row(cls, row, header: Header) -> InventoryRow | FailedRow:
        dto = InventoryDTO.sanitize(row, header)
        if isinstance(dto, FailedRow):
            return dto

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
        if cost_row.qty <= 0:
            self.excluded_dates.append(cost_row.date)
            print(
                "Potential data integrity error and purchases datasource 0 qty purchase row: ",
                cost_row,
            )
            return

        if self.unallocated == 0:
            self.excluded_dates.append(cost_row.date)
            return

        elif cost_row.qty >= self.unallocated:
            self.total_cost += self.unallocated * cost_row.unit_cost
            self.average_cost = self.total_cost / self.qty
            self.purchase_dates.append(cost_row.date)
            self.unallocated = Decimal(0)
            return

        elif cost_row.qty < self.unallocated:
            self.total_cost += cost_row.qty * cost_row.unit_cost
            self.unallocated -= cost_row.qty
            try:
                self.average_cost = self.total_cost / (self.qty - self.unallocated)
            except InvalidOperation, DivisionByZero:
                print("issue:", self.qty, cost_row.qty, self.unallocated, self.sku)
                self.average_cost = self.total_cost
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


@dataclass
class FailedRow:
    row: Any
    error: Exception
    context: str


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
        """Creates a Header instance with all necessary LandedCostRow mappings."""

        h = Header()
        h.sku = sku
        h.qty = qty
        h.unit_cost = unit_cost
        h.date = date
        h.date_format = date_format
        return h

    @classmethod
    def inventory_row(cls, sku, base_sku, inventory) -> Header:
        """Creates a Header instance with all necessary InventoryRow mappings."""

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
    def sanitize(cls, row, header: Header) -> InventoryDTO | FailedRow:
        dto = InventoryDTO()
        try:
            sku = str(row[header.sku])
            base_sku = str(row[header.base_sku])
            inventory = Decimal(row[header.inventory])
        except (ValueError, InvalidOperation, TypeError) as e:
            return FailedRow(
                row=row,
                error=e,
                context="Row contents contained at least one incompatible type.",
            )

        if sku != base_sku:
            return FailedRow(
                row=row, error=ValueError(), context="Base must be the same as sku."
            )
        if len([c for c in _INVALID_SKU_CHAR if c in sku]) > 0:
            return FailedRow(
                row=row, error=ValueError(), context="Sku contains invalid character. "
            )

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
    def sanitize(cls, row, header: Header) -> LandedCostDTO | FailedRow:
        dto = LandedCostDTO()
        try:
            sku = str(row[header.sku])
            qty = Decimal(row[header.qty])
            unit_cost = Decimal(row[header.unit_cost])
            date: dt | str = row[header.date]

        except (ValueError, TypeError) as e:
            return FailedRow(
                row=row,
                error=e,
                context="One or more elements of row are incompatible type.",
            )

        if qty <= 0:
            return FailedRow(
                row=row,
                error=ValueError(),
                context="Purchase qty must be greater than zero",
            )

        dto.sku = sku
        dto.qty = qty
        dto.unit_cost = unit_cost

        if not date:
            return FailedRow(
                row=row, error=ValueError(), context=" Purchase Must have valid date."
            )

        if not isinstance(date, dt):
            try:
                date = dt.strptime(date, header.date_format)
            except ValueError:
                return FailedRow(
                    row=row,
                    error=TypeError(),
                    context=f"Date value exists but is incompatible with {header.date_format}",
                )
        dto.date = date

        if not all(vars(dto)):
            return FailedRow(
                row=row, error=ValueError(), context="incomplete data in row."
            )
        return dto
