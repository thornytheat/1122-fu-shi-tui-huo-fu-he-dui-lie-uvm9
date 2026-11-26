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
class RiskVector:
    rma: str
    original_shop: str
    category: str
    arrival: int
    weight_z: float
    open_seal: float
    repeat_log: float
    extra_days: float
    found_mismatch: bool
    labeled: int


def parse(values: Mapping[str, Any]) -> RiskVector:
    if not isinstance(values, Mapping):
        raise InvalidRow('inspection_score', 'EXPECTED_OBJECT')
    rma = text(values, 'rma', 'inspection_score.rma')
    original_shop = text(values, 'original_shop', 'inspection_score.original_shop')
    category = text(values, 'category', 'inspection_score.category')
    arrival = integer(values, 'arrival', 0, 10000000, 'inspection_score.arrival')
    weight_z = number(values, 'weight_z', 0, 100, 'inspection_score.weight_z')
    open_seal = number(values, 'open_seal', 0, 1, 'inspection_score.open_seal')
    repeat_log = number(values, 'repeat_log', 0, 10, 'inspection_score.repeat_log')
    extra_days = number(values, 'extra_days', 0, 300, 'inspection_score.extra_days')
    found_mismatch = flag(values, 'found_mismatch', 'inspection_score.found_mismatch')
    labeled = integer(values, 'labeled', 0, 10000000, 'inspection_score.labeled')
    return RiskVector(
        rma=rma,
        original_shop=original_shop,
        category=category,
        arrival=arrival,
        weight_z=weight_z,
        open_seal=open_seal,
        repeat_log=repeat_log,
        extra_days=extra_days,
        found_mismatch=found_mismatch,
        labeled=labeled,
    )
