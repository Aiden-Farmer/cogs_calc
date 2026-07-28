from copy import copy
from decimal import Decimal
from typing import Callable, Iterable

from .datarows import RowLike, LandedCostRow

kit_ref: dict[str, dict[str, int]] = {}

def component_cost_allocation(
    total_cost: Decimal,
    component_kit_qty: Decimal,
    ALLOCATE_COMP_COST: int,
    total_components: Decimal,
    user_defined_cost_allocation=None,
) -> Decimal:
    """
    ALLOCATE_COMP_COST flag defines allocation behavior:
    0 for user defined cost allocation (kit_ref must be provided with % of total cost for each kit component).
    1 for even allocation across all kit components (accounting for quantity variance).

    """
    if not isinstance(total_cost, Decimal):
        raise TypeError("total_cost must be type Decimal")
    if not isinstance(component_kit_qty, Decimal):
        raise TypeError("Component kit quantity must be type Decimal")
    if not isinstance(total_components, Decimal):
        raise TypeError("total_components must be type Decimal")

    if total_cost < 0:
        raise ValueError("total_cost must be non-negative")
    if component_kit_qty <= 0:
        raise ValueError("component_kit_qty must be positive")
    if total_components <= 0:
        raise ValueError("total_components must be positive")

    def _allocate_quantity_based_cost() -> Decimal:
        return total_cost * component_kit_qty / total_components
    

    def _allocate_user_defined_cost() -> Decimal:
        if not user_defined_cost_allocation:
            raise ValueError(
                "When using ALLOCATE_COMP_COST=0 user must define cost_percent"
            )
        return total_cost * user_defined_cost_allocation

    match ALLOCATE_COMP_COST:
        case 0:
            return _allocate_user_defined_cost()
        case 1:
            return _allocate_quantity_based_cost()
        case _:
            raise ValueError("ALLOCATE_COMP_COST flag must be either 0 or one.")


def split_kits(
    func: Callable[..., Iterable[RowLike]], kit_ref=kit_ref, ALLOCATE_COMP_COST=0
) -> Callable[..., Iterable[RowLike]]:

    def wrapper(*args, **kwargs) -> Iterable[RowLike]:
        for item in func(*args, **kwargs):
            if not item:
                return

            if not isinstance(item, RowLike):
                raise TypeError(f"Expected Rowlike, got {type(item)}")

            if item.sku not in kit_ref:
                yield item
                return

            if isinstance(item, LandedCostRow):
                for c_sku, c_qty in kit_ref[item.sku]["components"].items():
                    c = copy(item)
                    c.sku = c_sku
                    c.qty = item.qty * c_qty
                    c.date = item.date
                    c.unit_cost = component_cost_allocation(
                        item.unit_cost,
                        c_qty,
                        ALLOCATE_COMP_COST,
                        kit_ref[item.sku]["total_components"],
                        kit_ref[item.sku].get("cost_percent"),
                    )
                    yield c
                return

            for c_sku, c_qty in kit_ref[item.sku]["components"].items():
                c = copy(item)
                c.sku = c_sku
                c.qty = item.qty * c_qty
                yield c

    return wrapper
