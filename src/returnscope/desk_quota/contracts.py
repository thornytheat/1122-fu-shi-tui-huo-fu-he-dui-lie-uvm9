from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any


class InvalidRow(ValueError):
    def __init__(self, field: str, code: str):
        super().__init__(f'{field}: {code}')
        self.field = field
        self.code = code


def number(row: Mapping, key: str, low: float, high: float, field: str) -> float:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise InvalidRow(field, 'EXPECTED_NUMBER')
    if not low <= value <= high or not math.isfinite(value):
        raise InvalidRow(field, 'OUT_OF_RANGE')
    return float(value)


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
class ReviewCandidate:
    rma: str
    original_shop: str
    category: str
    reason: str
    score: float
    in_scope: bool
    amount: int
    arrival: int
    priority: bool
    seal: bool


def parse(values: Mapping[str, Any]) -> ReviewCandidate:
    if not isinstance(values, Mapping):
        raise InvalidRow('desk_quota', 'EXPECTED_OBJECT')
    rma = text(values, 'rma', 'desk_quota.rma')
    original_shop = text(values, 'original_shop', 'desk_quota.original_shop')
    category = text(values, 'category', 'desk_quota.category')
    reason = text(values, 'reason', 'desk_quota.reason')
    score = number(values, 'score', 0, 1, 'desk_quota.score')
    in_scope = flag(values, 'in_scope', 'desk_quota.in_scope')
    amount = integer(values, 'amount', 1, 1000000, 'desk_quota.amount')
    arrival = integer(values, 'arrival', 0, 10000000, 'desk_quota.arrival')
    priority = flag(values, 'priority', 'desk_quota.priority')
    seal = flag(values, 'seal', 'desk_quota.seal')
    return ReviewCandidate(
        rma=rma,
        original_shop=original_shop,
        category=category,
        reason=reason,
        score=score,
        in_scope=in_scope,
        amount=amount,
        arrival=arrival,
        priority=priority,
        seal=seal,
    )
