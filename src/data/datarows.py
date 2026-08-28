from __future__ import annotations


import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime as dt
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import Any, Self

from typeguard import typechecked

logger = logging.getLogger("COGS")

_USER_TZ = UTC
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


class SalesRow(RowLike):
    """
    One sku's sales record: qty sold per channel over the period, read
    from a single wide sheet with one qty column per channel.
    """

    must_sort = False

    def __init__(self, row: SalesDTO) -> None:
        self.sku: str = row.sku
        self.qty: dict[str, Decimal] = row.qty

    def __repr__(self) -> str:
        return f"SalesRow(sku={self.sku!r}, qty={self.qty!r})"

    @classmethod
    def from_row(cls, row, header) -> SalesRow | FailedRow:
        dto = SalesDTO.sanitize(row, header)
        if isinstance(dto, FailedRow):
            return dto

        return cls(dto)


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

        self.sales = SalesData()
    
    @classmethod
    @typechecked # I do not believe this works as intended, see https://typeguard.readthedocs.io/en/latest/userguide.html#using-the-decorator. This method does not have meaningful type annotations.
    def from_row(cls, row, header: Header) -> InventoryRow | FailedRow:
        dto = InventoryDTO.sanitize(row, header)
        if isinstance(dto, FailedRow):
            return dto

        return cls(dto)

    def export(self) -> dict:
        row = {
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
        # One column per sales channel, continuing on from "g" above, then
        # one more per channel for sales value; order matches
        # SalesData.sales_qty/.sales_value's definition order, which
        # write_outfile relies on to build matching headers.
        qty_start = ord("h")
        for i, qty in enumerate(self.sales.sales_qty.values()):
            row[chr(qty_start + i)] = qty

        value_start = qty_start + len(self.sales.sales_qty)
        for j, val in enumerate(self.sales.sales_value.values()):
            row[chr(value_start + j)] = val

        return row

    def allocate_from_landed_cost(self, cost_row: LandedCostRow):
        if cost_row.qty <= 0:
            self.excluded_dates.append(cost_row.date)
            logger.warning(
                "Potential data integrity error and purchases datasource 0 qty purchase row: ",
                cost_row,
            )
            return

        if self.unallocated == 0:
            if not self.sales_value(cost_row):
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
                logger.error("issue:", self.qty, cost_row.qty, self.unallocated, self.sku)
                self.average_cost = self.total_cost
            self.purchase_dates.append(cost_row.date)


    def sales_value(self, cost_row):
        if (unallocated := (self.sales.total_sales - self.sales.allocated_sales)) <= 0:
            return False
        self.sales.total_cost += cost_row.unit_cost * min(unallocated, cost_row.qty)
        self.sales.allocated_sales += min(unallocated, cost_row.qty)

            # Last sale data needed, distrubute costs of sales to channels.
        if self.sales.allocated_sales == self.sales.total_sales:
            unit_cost = Decimal(self.sales.total_cost / self.sales.allocated_sales) 
            for channel, qty in self.sales.sales_qty.items():
                self.sales.sales_value[channel] = unit_cost * qty    

    def record_sale(self, channel: str, qty: int):
        if channel not in self.sales.sales_qty:
            logger.warning("%s missing from SalesData defined channels", channel)
            return
        self.sales.sales_qty[channel] += qty
        self.sales.total_sales += qty
 

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
    as_of_date: dt | None = None
    channel_columns: dict[str, int]

    @classmethod
    def landed_cost(
        cls,
        sku,
        qty,
        unit_cost,
        date,
        date_format="%Y-%m-%d",
        as_of_date: dt | None = None,
    ) -> Header:
        """Creates a Header instance with all necessary LandedCostRow mappings."""

        h = Header()
        h.sku = sku
        h.qty = qty
        h.unit_cost = unit_cost
        h.date = date
        h.date_format = date_format
        h.as_of_date = as_of_date
        return h

    @classmethod
    def inventory_row(cls, sku, base_sku, inventory) -> Header:
        """Creates a Header instance with all necessary InventoryRow mappings."""

        h = Header()
        h.sku = sku
        h.base_sku = base_sku
        h.inventory = inventory
        return h

    @classmethod
    def transfer_row(cls, to_sku, from_sku, qty, date, date_format) -> Header:
        """Creates a Header instance with all necessary LandedCostRow mappings."""

        h = Header()
        h.sku = to_sku
        h.base_sku = from_sku
        h.qty = qty
        h.date = date
        h.date_format = date_format
        return h

    @classmethod
    def sales_row(cls, sku, channel_columns: dict[str, int]) -> Header:
        """Creates a Header instance with all necessary SalesRow mappings.

        channel_columns maps each sales channel name (matching
        SalesData.sales_qty's keys) to its 0-indexed qty column on the
        sheet -- one sku per row, one qty column per channel.
        """

        h = Header()
        h.sku = sku
        h.channel_columns = channel_columns
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

        except (ValueError, InvalidOperation, TypeError) as e:
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
                date = dt.strptime(date, header.date_format)  # noqa: DTZ007 -- stamped with _USER_TZ below rather than assumed local.
            except ValueError:
                return FailedRow(
                    row=row,
                    error=TypeError(),
                    context=f"Date value exists but is incompatible with {header.date_format}",
                )

        if date.tzinfo is None:
            date = date.replace(tzinfo=_USER_TZ)

        if header.as_of_date and date > header.as_of_date:
            context = (
                f"Purchase dated {date:%Y-%m-%d} is after "
                f"as_of_date {header.as_of_date:%Y-%m-%d}; excluded."
            )
            logger.info(context, row)
            return FailedRow(row=row, error=ValueError(), context=context)

        dto.date = date

        if not all(vars(dto).values()):
            return FailedRow(
                row=row, error=ValueError(), context="incomplete data in row."
            )
        return dto


class SalesDTO:
    sku: str
    qty: dict[str, Decimal]

    @classmethod
    def sanitize(cls, row, header: Header) -> SalesDTO | FailedRow:
        dto = SalesDTO()
        try:
            sku = str(row[header.sku])
        except (ValueError, TypeError) as e:
            return FailedRow(
                row=row, error=e, context="Sku column is an incompatible type."
            )

        if not sku:
            return FailedRow(
                row=row, error=ValueError(), context="incomplete data in row."
            )

        qty_by_channel: dict[str, Decimal] = {}
        for channel, col in header.channel_columns.items():
            value = row[col]
            if value is None or value == "":
                continue  # sku didn't sell on this channel over the period

            try:
                qty = Decimal(value)
            except (ValueError, InvalidOperation, TypeError) as e:
                return FailedRow(
                    row=row,
                    error=e,
                    context=f"{channel} qty is an incompatible type.",
                )

            if qty < 0:
                return FailedRow(
                    row=row,
                    error=ValueError(),
                    context=f"{channel} qty must not be negative.",
                )

            if qty > 0:
                qty_by_channel[channel] = qty

        dto.sku = sku
        dto.qty = qty_by_channel
        return dto


class SalesData:
    def __init__(self):
        self.sales_qty = {
            "Amazon": 0,
            "eBay": 0,
            "Etsy": 0,
            "Houzz": 0,
            "Shopify": 0,
            "Walmart": 0,
            "Wayfair": 0,
        }

        self.sales_value = {
            "Amazon": 0,
            "eBay": 0,
            "Etsy": 0,
            "Houzz": 0,
            "Shopify": 0,
            "Walmart": 0,
            "Wayfair": 0,
        }
        self.total_sales = 0
        self.allocated_sales = 0
        self.total_cost = 0
    
     
