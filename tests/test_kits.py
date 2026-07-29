from unittest import mock

from inventory_kits.reader import ExcelKitReader


class TestKitReader:

    def test_reader_raises_when_row_data_incomplete(self):
        x = ExcelKitReader()