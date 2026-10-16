
from openpyxl import Workbook
from openpyxl.chartsheet import Chartsheet 

from src.data.data_exception import DataSourceError

_filter_sheet_name = "Filters"

def return_sellercloud_metadata(fd: Workbook):
        if not _filter_sheet_name in fd.sheetnames:
            raise DataSourceError(f"File provided does not have Filters sheet, instead has {fd.sheetnames}")

        ws = fd[_filter_sheet_name]
        if isinstance(ws, Chartsheet):
            raise DataSourceError

        for row in ws.values:
            yield row
