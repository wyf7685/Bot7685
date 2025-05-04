import contextlib
import functools
import operator
from collections.abc import Callable, Container, Iterable
from typing import Any, TypedDict, cast

type _Value = str | float | list[_Value]


def convert_wrapper[T1, T2](func: Callable[[T1, T2], bool]) -> Callable[[T1, T2], bool]:
    @functools.wraps(func)
    def wrapper(a: T1, b: T2) -> bool:
        def convert(value: object) -> Any:
            if isinstance(value, str):
                value = value.removesuffix("%")
                with contextlib.suppress(ValueError):
                    value = float(value)
            elif isinstance(value, list):
                return [convert(item) for item in cast("list[object]", value)]
            return value

        return func(convert(a), convert(b))

    return wrapper


@convert_wrapper
def func_in(a: object, b: Container[object]) -> bool:
    if isinstance(a, list):
        return any(i in b for i in cast("list[object]", a))

    return a in b


@convert_wrapper
def func_not_in(a: object, b: Container[object]) -> bool:
    if isinstance(a, list):
        return all(i not in b for i in cast("list[object]", a))
    return a not in b


COMPARISON_OPERATIONS: dict[str, Callable[[Any, Any], object]] = {
    "=": convert_wrapper(operator.eq),
    "!=": convert_wrapper(operator.ne),
    "<": convert_wrapper(operator.lt),
    ">": convert_wrapper(operator.gt),
    "<=": convert_wrapper(operator.le),
    ">=": convert_wrapper(operator.ge),
    "in": func_in,
    "!in": func_not_in,
}


class _ExpressionDict(TypedDict):
    choose: str
    key: str
    op: str
    value: str
    sub: list["_ExpressionDict"]


class ExpressionEvaluator:
    def __init__(self, ctx: dict[str, object]) -> None:
        self.ctx: dict[str, object] = ctx

    def evaluate(self, expression: _ExpressionDict) -> bool:
        return self._evaluate_expression(expression["op"], expression)

    def _evaluate_expression(self, op: str, expression: _ExpressionDict) -> bool:
        if op in {"&&", "||", "!"}:
            return self._evaluate_logical(op, expression["sub"])
        return self._evaluate_comparison(expression)

    def _evaluate_logical(self, op: str, childs: list[_ExpressionDict]) -> bool:
        def _(v: Iterable[object], /) -> bool:
            return not next(iter(v))

        operation = {"&&": all, "||": any, "!": _}[op]
        return operation(self.evaluate(child) for child in childs)

    def _evaluate_comparison(self, expression: _ExpressionDict) -> bool:
        key, op, value = expression["key"], expression["op"], expression["value"]
        return key in self.ctx and bool(COMPARISON_OPERATIONS[op](self.ctx[key], value))


def find_first_matching_expression(
    ctx: dict[str, object],
    expressions: list[_ExpressionDict],
) -> str | None:
    evaluator = ExpressionEvaluator(ctx)
    for expr in expressions:
        with contextlib.suppress(Exception):
            if evaluator.evaluate(expr):
                return expr["choose"]
    return None
