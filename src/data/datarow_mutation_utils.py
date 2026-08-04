from collections.abc import Callable, Iterator
from copy import copy
from decimal import Decimal
from pathlib import Path
from pickle import loads
from typing import TypeVar

from .datarows import FailedRow, LandedCostRow, RowLike

kit_ref_path = Path.cwd() / "private" / "kits.obj"
cost_ref_path = Path.cwd() / "private" / "costs.obj"

try:
    with open(kit_ref_path, "rb") as fd:
        kit_ref = loads(fd.read())
except EOFError, FileNotFoundError:  # EOFError to cover file exists but no data
    print("Kits.obj has no data, program will be unable to split kits.")
    kit_ref = {}

try:
    with open(cost_ref_path, "rb") as fd:
        cost_ref = loads(fd.read())
except EOFError, FileNotFoundError:  # EOFError to cover file  exists but no data
    print(
        "costs.obj has no data, program will be unable to allocate component costs on a value basis."
    )
    cost_ref = {}


def component_cost_allocation(
    total_cost: Decimal,
    component_kit_qty: int,
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
    if not isinstance(component_kit_qty, int):
        raise TypeError("Component kit quantity must be type int")
    if ALLOCATE_COMP_COST == 1 and not isinstance(total_components, Decimal):
        raise TypeError("total_components must be type Decimal")

    if total_cost < 0:
        raise ValueError("total_cost must be non-negative")
    if component_kit_qty <= 0:
        raise ValueError("component_kit_qty must be positive")
    if ALLOCATE_COMP_COST == 1 and total_components <= 0:
        raise ValueError("total_components must be positive")

    def _allocate_quantity_based_cost() -> Decimal:
        return total_cost * component_kit_qty / total_components

    def _allocate_user_defined_cost() -> Decimal:

        if user_defined_cost_allocation is None:
            raise ValueError(
                "When using ALLOCATE_COMP_COST=0 user must define pc_total_cost"
            )
        return total_cost * user_defined_cost_allocation

    match ALLOCATE_COMP_COST:
        case 0:
            return _allocate_user_defined_cost()
        case 1:
            return _allocate_quantity_based_cost()
        case _:
            raise ValueError("ALLOCATE_COMP_COST flag must be either 0 or one.")


T = TypeVar("T", bound="RowLike")


def split_kits(  # noqa: UP047
    # https://docs.astral.sh/ruff/rules/non-pep695-generic-class/
    # This rule can only offer a fix if all of the generic types in the class definition are defined in the current module.
    # For external type parameters, a diagnostic is emitted without a suggested fix.
    func: Callable[..., Iterator[T | FailedRow]],
    kit_ref=kit_ref,
    ALLOCATE_COMP_COST=0,
) -> Callable[..., Iterator[T | FailedRow]]:

    def wrapper(*args, **kwargs) -> Iterator[T]:
        for item in func(*args, **kwargs):
            if isinstance(item, FailedRow):
                continue

            if not isinstance(item, RowLike):
                raise TypeError(f"Expected Rowlike, got {type(item)}")

            if item.sku not in kit_ref:
                yield item
                continue

            if isinstance(item, LandedCostRow):
                for c_sku, c_info in (
                    kit_ref[item.sku].items()
                ):  # c_info: {"qty": int, "cost": Decimal, "pc_of_total_cost": Decimal}
                    c = copy(item)
                    c.sku = c_sku
                    c.qty = item.qty * c_info["qty"]
                    c.date = item.date
                    c.unit_cost = component_cost_allocation(
                        total_cost=item.unit_cost,
                        component_kit_qty=c_info["qty"],
                        ALLOCATE_COMP_COST=ALLOCATE_COMP_COST,
                        total_components=c_info.get("total_components"),
                        user_defined_cost_allocation=c_info["pc_of_total_cost"],
                    )
                    yield c
                continue
            else:
                for c_sku, c_info in kit_ref[item.sku].items():
                    c = copy(item)
                    c.sku = c_sku
                    c.qty = item.qty * c_info["qty"]
                    yield c

    return wrapper
