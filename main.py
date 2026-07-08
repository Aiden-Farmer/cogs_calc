from datetime import datetime as dt
import openpyxl as xl

from typing import Iterator, Generic,  TypeVar, Type, Self
from abc import ABC, abstractmethod
import msoffcrypto
import io
from getpass import getpass
from warnings import filterwarnings
from zipfile import BadZipFile

class RowLike(ABC):
    has_wb_conditions: bool = False

    def __init__(self, row: list[str]):
        self.sku = row[0]

    @classmethod
    @abstractmethod
    def from_row(cls, row) -> Self|None:
        row_like = cls(row)
        return row_like
    
    def allocate_from_landed_cost(self, cost_row):
        raise NotImplementedError("This is an optional method that is not valdi for all types of RowLike")
    
    

T = TypeVar("T", bound="RowLike")
class Reader(Generic[T]):
    def __init__(self, wb_path, ws_name, return_type: Type[T]):

        try:
            wb = xl.load_workbook(filename=wb_path, read_only=True, data_only=True)
        except BadZipFile as e:
            decrypted = self._handle_password_protected(filename=wb_path)
            if decrypted is None:
                raise BadZipFile(f"{wb_path} is either not a valid xlsx or could not be decrypted") from e
            wb = xl.load_workbook(filename=decrypted, read_only=True, data_only=True)

        self.ws = wb[ws_name]
        self.rt: Type[T] = return_type
        

    def readlineo(self) -> Iterator[T]:
        for i, raw in enumerate(self.ws.iter_rows(values_only=True)):
            #Skip headers row
            if i == 0:
                continue
            # if raw is None:
            #     raise StopIteration
            
            if (row := self.rt.from_row(raw)):
                yield row 

            

    @staticmethod
    def _handle_password_protected(filename) -> io.BytesIO|None:
        decrypted = io.BytesIO()
        try:
            with open(filename, 'rb') as f:
                header = f.read(8)
                if header != b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
                    return None
                
                u_input_pass = getpass(f"{filename} is password protected, please enter password: ")
                file = msoffcrypto.OfficeFile(f)
                file.load_key(password=u_input_pass)
                file.decrypt(decrypted)
                return decrypted
        except BadZipFile:
            return None


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
            'sku': 3,
            'base_sku': 2,
            'inventory': 28
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
            or (row[cls.header['sku']] != row[cls.header['base_sku']])
            or (" " in str(row[cls.header['sku']]))
            or (any(row[col_num] == exclusion_val for col_num, exclusion_val in cls.user_defined.items()))
        ):
            # print(f"{row} rejected")
            return None
        
        return cls(row)

    def allocate_from_landed_cost(self, cost_row: LandedCostRow):
        if self.unallocated == 0:
            self.excluded_dates.append(cost_row.date)
            return
    
        elif cost_row.qty >= self.unallocated:
            if cost_row.sku == 'CH-S50-16-BLK':
                print(f"{self}, allocating {cost_row}")
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



def main():
    
    inv_reader = Reader('inventory.xlsx', 'Inventory', InventoryRow)
    cost_reader = Reader('landed cost.xlsx', 'PURCHASES', LandedCostRow)
    mrd = dt.max
    inventory: dict[str, InventoryRow] = {}

    for inv_row in inv_reader.readlineo():
        inventory[inv_row.sku] = inv_row

    for i, cost_row in enumerate(cost_reader.readlineo()):
        if cost_row.date > mrd:
            raise ValueError('Landed Cost field is not sorted Newest to Oldest')
        mrd = cost_row.date
        if not cost_row.sku in inventory:
            continue
        inventory[cost_row.sku].allocate_from_landed_cost(cost_row)
        del cost_row
    

    #write outfile
    wb = xl.Workbook()
    ws = wb.active
    if not ws:
        raise ValueError
    ws.title = "Inventory Asset Value"
    ws.append(["Sku", "total Cost", "Average Cost", "Inventory"])

    for item in inventory.values():
        ws.append([item.sku, item.total_cost, item.average_cost, item.inventory])

    wb.save('outfile.xlsx')




if __name__ == "__main__":
    main()

    