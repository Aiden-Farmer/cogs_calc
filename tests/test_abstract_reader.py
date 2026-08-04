from __future__ import annotations

import pytest

from src.data.datarows import FailedRow
from src.data.reader import AbstractReader, RowLikeConfigError


class _FakeRowLike:
    must_sort = False

    def __init__(self, value):
        self.value = value

    @classmethod
    def from_row(cls, row, header):
        if row == "bad":
            return FailedRow(row=row, error=ValueError(), context="bad row")
        return cls(row)


class _FakeSortedRowLike(_FakeRowLike):
    must_sort = True

    @classmethod
    def sort_key(cls, row):
        return row.value


class _FakeSortedNoKeyRowLike:
    must_sort = True

    @classmethod
    def from_row(cls, row, header):
        return _FakeRowLike(row)


class _FakeReader(AbstractReader):
    def _initialize_data(self, ds):
        return ds

    def _iter_raw(self):
        return iter(self.data)


class TestAbstractReaderReadline:
    def test_filters_out_failed_rows_and_yields_valid_ones(self):
        reader = _FakeReader(
            data_source=["ok1", "bad", "ok2"], header=None, return_type=_FakeRowLike
        )

        rows = list(reader.readline())

        assert [r.value for r in rows] == ["ok1", "ok2"]

    def test_sorts_by_sort_key_descending_when_must_sort(self):
        reader = _FakeReader(data_source=[1, 3, 2], header=None, return_type=_FakeSortedRowLike)

        rows = list(reader.readline())

        assert [r.value for r in rows] == [3, 2, 1]

    def test_raises_rowlikeconfigerror_when_must_sort_true_without_sort_key(self):
        reader = _FakeReader(
            data_source=[1, 2], header=None, return_type=_FakeSortedNoKeyRowLike
        )

        with pytest.raises(RowLikeConfigError):
            list(reader.readline())


class TestAbstractReaderContextManagement:
    def test_enter_returns_self(self):
        reader = _FakeReader(data_source=[], header=None, return_type=_FakeRowLike)

        with reader as ctx:
            assert ctx is reader

    def test_exit_calls_close(self):
        closed = []

        class _ClosingReader(_FakeReader):
            def close(self) -> None:
                closed.append(True)

        with _ClosingReader(data_source=[], header=None, return_type=_FakeRowLike):
            pass

        assert closed == [True]

    def test_default_close_is_a_noop(self):
        reader = _FakeReader(data_source=[], header=None, return_type=_FakeRowLike)

        assert reader.close() is None
