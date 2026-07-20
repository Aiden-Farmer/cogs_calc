from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from collections.abc import Generator
from collections.abc import Iterable
from typing import Any
from typing import Generic
from typing import TypeVar

from data.datarows import Header
from data.datarows import RowLike


T = TypeVar("T", bound="RowLike")
DS = TypeVar("DS")


class AbstractReader(ABC, Generic[T, DS]):
    def __init__(self, data_source: DS, header: Header, return_type: type[T]):
        self.data: Any = self._initialize_data(data_source)
        self.rt: type[T] = return_type
        self.header: Header = header

    def readline(self) -> Generator[T]:
        rows: Generator[T | None] = (
            self.rt.from_row(
                raw,
                self.header,
            )
            for raw in self._iter_raw()
        )
        valid_rows: Iterable[T] = (r for r in rows if r is not None)

        if not self.rt.must_sort:
            yield from valid_rows
            return

        sort_key = getattr(self.rt, "sort_key", None)
        if not sort_key:
            raise RowLikeConfigError(
                "Sort_key must be defined on RowLike object.",
            )
        yield from sorted(valid_rows, key=sort_key, reverse=True)

    @abstractmethod
    def _initialize_data(self, ds) -> Any: ...

    @abstractmethod
    def _iter_raw(self) -> Iterable: ...

    def close(self) -> None:
        """Default no-op; override where teardown needed."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class RowLikeConfigError(BaseException):
    pass
