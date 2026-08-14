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
    excel,
)

from src.transfers.transfer_rows import TransferRow
from src.transfers.reader import TransferFileReader

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

    return TransferFileReader(filename = file_path, header = header) 


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
            # While builing Inventory structure we have not allocated any purchases to inventory,
            # so unallocated == qty
            inventory[inv_row.sku].unallocated = inventory[inv_row.sku].qty
        else:
            inventory[inv_row.sku] = inv_row

    if not inventory:
        raise DataSourceError

    return inventory, failed_rows


def allocate_landed_costs(
        cost_reader: excel.Reader[LandedCostRow], inventory: dict[str, InventoryRow], transfers: dict[str, TransferRow]
) -> list[FailedRow]:

    def _allocator(cost_row: LandedCostRow, inventory: dict[str, InventoryRow], transfers: dict[str, TransferRow]
) -> None:
        if cost_row.sku in transfers:
            transfer_row = transfers[cost_row.sku]
            if inventory[transfer_row.from_sku].unallocated != 0:
                inventory[cost_row.sku].allocate_from_landed_cost(cost_row)
            
            elif inventory[transfer_row.from_sku].unallocated == 0:
                target_row = inventory[transfer_row.to_sku]
                if cost_row.qty > transfer_row.qty:
                    cost_row.qty = transfer_row.qty
                target_row.allocate_from_landed_cost(cost_row)

                transfer_row.qty -=  
                

        inventory[cost_row.sku].allocate_from_landed_cost(cost_row)




    failed_rows: list[FailedRow] = []
    for cost_row in tqdm(cost_reader.readline(), desc="Reading purchase records"):
        if isinstance(cost_row, FailedRow):
            failed_rows.append(cost_row)
            continue


        if cost_row.sku not in inventory or cost_row.sku not in transfers:
            failed_rows.append(
                FailedRow(
                    row=cost_row,
                    error=ValueError(),
                    context="Purchase for item that is not in inventory.",
                )
            )
            continue

        _allocator(cost_row, inventory,transfers)

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
    ws.append(
        [
            "SKU",
            "Inventory Cost",
            "Unallocated",
            "Dates Received",
            "Dates received not counting against Average Cost",
            "Total Cost",
            "Average Cost",
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
            print("'outfile.xlsx is in use, please close it to complete program.")
            uin = input(
                "Once the file is closed, enter [yes] or [y] to get output, any other input will terminate the program: "
            )
            if uin not in {"y", "yes"}:
                break
