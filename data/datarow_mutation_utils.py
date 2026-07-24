from datarows import RowLike
from copy import copy

from typing import Callable, Optional

# figure out how to set this
kit_ref: dict[str, dict[str, int]] = {}


def split_kits(func: Callable[..., Optional[RowLike]]):
    def wrapper(*args, **kwargs):
        item = func(*args, **kwargs)
        if item is None:
            return
        if not isinstance(item, RowLike):
            raise TypeError(f"Expected Rowlike, got {type(item)}")

        if item.sku not in kit_ref:
            yield item
            return
        
        for c_sku, c_qty in kit_ref[item.sku].items():
                c = copy(item)
                c.sku = c_sku
                c.qty = item.qty * c_qty # Multiply parent inventory level by kit component qty 
                yield c
    return wrapper