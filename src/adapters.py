import logging

logger = logging.getLogger("COGS")

from os import startfile
from typing import TypeVar

import openpyxl as xl
from tqdm import tqdm

from src.data import (
    DataSourceError,
    FailedRow,
    Header,
    InventoryRow,
    LandedCostRow,
    RowLike,
    SalesData,
    SalesRow,
    excel,
)
from src.transfers.reader import TransferFileReader
from src.transfers.transfer_rows import TransferRow

T = TypeVar("T", bound=RowLike)


def give_reader(  # noqa: UP047
    file_path: str, sheet_name: str, header: Header, return_type: type[T]
) -> excel.Reader[T]:
    if not file_path.endswith(".xlsx"):
        raise TypeError(
            f"{return_type.__name__} file must be \
            .xlsx file type."
        )
    data_source = excel.Source(file_path, sheet_name)
    return excel.Reader(data_source, header, return_type)


def give_transfer_reader(
    file_path: str, sheet_name: str, header: Header
) -> TransferFileReader:

    assert sheet_name
    if not file_path.endswith(".xlsx"):
        raise TypeError()

    return TransferFileReader(filename=file_path, sheet_name=sheet_name, header=header)


def build_inventory(
    inv_reader: excel.Reader[InventoryRow],
) -> tuple[dict[str, InventoryRow], list[FailedRow]]:
    inventory: dict[str, InventoryRow] = {}
    failed_rows: list[FailedRow] = []
    for inv_row in tqdm(inv_reader.readline(), desc="Building Inventory"):
        if isinstance(inv_row, FailedRow):
            failed_rows.append(inv_row)
            continue

        elif inv_row.sku in inventory:
            inventory[inv_row.sku].qty += inv_row.qty
            inventory[inv_row.sku].unallocated = inventory[inv_row.sku].qty
        else:
            inventory[inv_row.sku] = inv_row

    if not inventory:
        raise DataSourceError

    return inventory, failed_rows


def build_transfers(
    trans_reader: TransferFileReader,
) -> tuple[dict[str, TransferRow], list[FailedRow]]:
    transfers: dict[str, TransferRow] = {}
    failed_rows: list[FailedRow] = []

    for trans_row in tqdm(trans_reader.readline(), desc="Building Transfer dictionary"):
        if isinstance(trans_row, FailedRow):
            failed_rows.append(trans_row)
            continue

        elif trans_row.from_sku in transfers:
            if trans_row.to_sku != transfers[trans_row.from_sku].to_sku:
                raise DataSourceError(
                    f"Transfer of sku {trans_row.from_sku} to {trans_row.to_sku} "
                    "already has existing transfer to other sku "
                    f"{transfers[trans_row.from_sku].to_sku}."
                )

            transfers[trans_row.from_sku].qty += trans_row.qty
        else:
            transfers[trans_row.from_sku] = trans_row

    return transfers, failed_rows


def record_sales(
    sales_reader: excel.Reader[SalesRow],
    inventory: dict[str, InventoryRow],
) -> list[FailedRow]:
    failed_rows: list[FailedRow] = []
    for sale_row in tqdm(sales_reader.readline(), desc="Reading sales records"):
        if isinstance(sale_row, FailedRow):
            failed_rows.append(sale_row)
            continue

        if sale_row.sku not in inventory:
            failed_rows.append(
                FailedRow(
                    row=sale_row,
                    error=ValueError(),
                    context="Sale for item that is not in inventory.",
                )
            )
            continue

        for channel, qty in sale_row.qty.items():
            inventory[sale_row.sku].record_sale(channel, int(qty))

    return failed_rows


def allocate_landed_costs(
    cost_reader: excel.Reader[LandedCostRow],
    inventory: dict[str, InventoryRow],
    transfers: dict[str, TransferRow] | None = None,
) -> list[FailedRow]:

    def _allocator(
        cost_row: LandedCostRow,
        inventory: dict[str, InventoryRow],
        transfers: dict[str, TransferRow],
    ) -> None:
        if cost_row.sku not in transfers:
            inventory[cost_row.sku].allocate_from_landed_cost(cost_row)
            return

        transfer_row = transfers[cost_row.sku]
        if inventory[transfer_row.from_sku].unallocated != 0:
            inventory[cost_row.sku].allocate_from_landed_cost(cost_row)
            return

        target_row = inventory[transfer_row.to_sku]
        original_qty = cost_row.qty
        redirected_qty = min(cost_row.qty, transfer_row.qty)
        cost_row.qty = redirected_qty
        target_row.allocate_from_landed_cost(cost_row)

        transfer_row.qty -= redirected_qty
        if transfer_row.qty == 0:
            del transfers[cost_row.sku]

        leftover_qty = original_qty - redirected_qty
        if leftover_qty > 0:
            cost_row.qty = leftover_qty
            inventory[cost_row.sku].allocate_from_landed_cost(cost_row)

    failed_rows: list[FailedRow] = []
    for cost_row in tqdm(cost_reader.readline(), desc="Reading purchase records"):
        if isinstance(cost_row, FailedRow):
            failed_rows.append(cost_row)
            continue

        if not cost_row.qty:
            # Purchases data does not gaurantee rows that have a total_cost and/or unit_cost value(s) will have a qty > 0.
            failed_rows.append(cost_row)
            continue

        if cost_row.sku not in inventory:
            failed_rows.append(
                FailedRow(
                    row=cost_row,
                    error=ValueError(),
                    context="Purchase for item that is not in inventory.",
                )
            )
            continue

        if not transfers:
            transfers = {}
        _allocator(cost_row, inventory, transfers)

    return failed_rows


def write_outfile(
    inventory: dict[str, InventoryRow], outfile_name: str = "outfile.xlsx"
):
    """write results of average cost calculation to file"""
    wb = xl.Workbook()
    ws = wb.active
    if not ws:
        raise ValueError
    ws.title = "Inventory Asset Value"
    # Channel names, in the same order InventoryRow.export() writes their
    # qty (then value) columns in -- both derive from SalesData.sales_qty's
    # definition order, which export() anchors the value columns' start on.
    channels = list(SalesData().sales_qty.keys())
    ws.append(
        [
            "SKU",
            "Inventory Cost",
            "Unallocated",
            "Dates Received",
            "Dates received not counting against Average Cost",
            "Total Cost",
            "Average Cost",
            *channels,
            *(f"{channel} Value" for channel in channels),
        ]
    )
    for item in inventory.values():
        ws.append(item.export())

    while True:
        try:
            wb.save(outfile_name)
            startfile(outfile_name)
            break
        except PermissionError:
            logger.error(
                "'outfile.xlsx is in use, please close it to complete program."
            )
            uin = input(
                "Once the file is closed, enter [yes] or [y] to get output, any other input will terminate the program: "
            )
            if uin not in {"y", "yes"}:
                break
