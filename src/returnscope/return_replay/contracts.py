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
class RefundEvidence:
    rma: str
    shop: str
    score: float
    amount: int
    mismatch: bool
    reviewed: bool
    arrival: int
    closed: int


def parse(values: Mapping[str, Any]) -> RefundEvidence:
    if not isinstance(values, Mapping):
        raise InvalidRow('return_replay', 'EXPECTED_OBJECT')
    rma = text(values, 'rma', 'return_replay.rma')
    shop = text(values, 'shop', 'return_replay.shop')
    score = number(values, 'score', 0, 1, 'return_replay.score')
    amount = integer(values, 'amount', 1, 1000000, 'return_replay.amount')
    mismatch = flag(values, 'mismatch', 'return_replay.mismatch')
    reviewed = flag(values, 'reviewed', 'return_replay.reviewed')
    arrival = integer(values, 'arrival', 0, 10000000, 'return_replay.arrival')
    closed = integer(values, 'closed', 0, 10000000, 'return_replay.closed')
    return RefundEvidence(
        rma=rma,
        shop=shop,
        score=score,
        amount=amount,
        mismatch=mismatch,
        reviewed=reviewed,
        arrival=arrival,
        closed=closed,
    )
