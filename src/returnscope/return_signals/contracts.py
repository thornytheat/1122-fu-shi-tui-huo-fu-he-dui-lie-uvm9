from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class InvalidRow(ValueError):
    def __init__(self, field: str, code: str):
        super().__init__(f'{field}: {code}')
        self.field = field
        self.code = code


def integer(row: Mapping, key: str, low: int, high: int, field: str) -> int:
    value = row.get(key)
    if type(value) is not int:
        raise InvalidRow(field, 'EXPECTED_INTEGER')
    if not low <= value <= high:
        raise InvalidRow(field, 'OUT_OF_RANGE')
    return value


def text(row: Mapping, key: str, field: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidRow(field, 'EXPECTED_NONEMPTY_TEXT')
    if len(value.strip()) > 80:
        raise InvalidRow(field, 'TEXT_TOO_LONG')
    return value.strip()


def flag(row: Mapping, key: str, field: str) -> bool:
    value = row.get(key)
    if type(value) is not bool:
        raise InvalidRow(field, 'EXPECTED_FLAG')
    return value


@dataclass(frozen=True, slots=True)
class ExpectedPackage:
    rma: str
    original_shop: str
    category: str
    arrival: int
    submitted: int
    weight: int
    listed_weight: int
    prior_returns: int
    seal: bool
    amount: int
    priority: bool


def parse(values: Mapping[str, Any]) -> ExpectedPackage:
    if not isinstance(values, Mapping):
        raise InvalidRow('return_signals', 'EXPECTED_OBJECT')
    rma = text(values, 'rma', 'return_signals.rma')
    original_shop = text(values, 'original_shop', 'return_signals.original_shop')
    category = text(values, 'category', 'return_signals.category')
    arrival = integer(values, 'arrival', 0, 10000000, 'return_signals.arrival')
    submitted = integer(values, 'submitted', 0, 10000000, 'return_signals.submitted')
    weight = integer(values, 'weight', 1, 90000, 'return_signals.weight')
    listed_weight = integer(values, 'listed_weight', 1, 90000, 'return_signals.listed_weight')
    prior_returns = integer(values, 'prior_returns', 0, 100, 'return_signals.prior_returns')
    seal = flag(values, 'seal', 'return_signals.seal')
    amount = integer(values, 'amount', 1, 1000000, 'return_signals.amount')
    priority = flag(values, 'priority', 'return_signals.priority')
    return ExpectedPackage(
        rma=rma,
        original_shop=original_shop,
        category=category,
        arrival=arrival,
        submitted=submitted,
        weight=weight,
        listed_weight=listed_weight,
        prior_returns=prior_returns,
        seal=seal,
        amount=amount,
        priority=priority,
    )
