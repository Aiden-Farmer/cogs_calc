from collections.abc import Sequence
from datetime import UTC
from datetime import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Any, Self

from ..data.datarows import FailedRow, Header, RowLike

_USER_TZ = UTC


class TransferRow(RowLike):
    def __init__(self, row: TransferDTO):
        self.from_sku: str = row.from_sku
        self.to_sku: str = row.to_sku
        self.qty: Decimal = row.qty
        self.date: dt = row.date

    @classmethod
    def from_row(cls, row: Sequence[Any], header: Header) -> Self | FailedRow:
        dto = TransferDTO.sanitize(row, header)
        if isinstance(dto, FailedRow):
            return dto
        return cls(dto)


class TransferDTO:
    to_sku: str
    from_sku: str
    qty: Decimal
    date: dt

    @classmethod
    def sanitize(cls, row, header: Header) -> TransferDTO | FailedRow:
        dto = TransferDTO()
        try:
            from_sku = str(row[header.base_sku])
            to_sku = str(row[header.sku])
            qty = Decimal(row[header.qty])
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
                context="Transfer qty must be greater than zero",
            )

        if not date:
            return FailedRow(
                row=row, error=ValueError(), context="Transfer must have valid date."
            )

        if not isinstance(date, dt):
            try:
                date = dt.strptime(date, header.date_format)  # noqa: DTZ007 -- stamped with _USER_TZ below rather than assumed local.
            except ValueError:
                return FailedRow(
                    row=row,
                    error=TypeError(),
                    context=f"Date value {date} exists but is incompatible with {header.date_format}",
                )

        if date.tzinfo is None:
            date = date.replace(tzinfo=_USER_TZ)

        dto.to_sku = to_sku
        dto.from_sku = from_sku
        dto.qty = qty
        dto.date = date

        if not all(vars(dto).values()):
            return FailedRow(
                row=row, error=ValueError(), context="incomplete data in row."
            )

        return dto
