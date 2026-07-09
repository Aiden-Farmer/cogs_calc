import io
from typing import TypeVar, Type, Generic, Iterator
import openpyxl as xl
from zipfile import BadZipFile
import msoffcrypto
import io
from getpass import getpass

from data.datarows import RowLike 


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

