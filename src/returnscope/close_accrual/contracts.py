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
class AccrualItem:
    """截止点仍挂在退款台账上的授权单。"""

    rma: str
    shop: str
    amount: int
    score: float
    in_scope: bool
    reviewed: bool
    refund_instruction: bool
    has_label: bool
    authorization_conflict: bool
    arrival: int


@dataclass(frozen=True, slots=True)
class ClosingEvidence:
    """退货复盘的结案证据，只在截止点前生效。"""

    rma: str
    shop: str
    amount: int
    mismatch: bool
    reviewed: bool
    arrival: int
    closed: int


def parse_item(values: Mapping[str, Any]) -> AccrualItem:
    if not isinstance(values, Mapping):
        raise InvalidRow('close_accrual', 'EXPECTED_OBJECT')
    return AccrualItem(
        rma=text(values, 'rma', 'close_accrual.rma'),
        shop=text(values, 'shop', 'close_accrual.shop'),
        amount=integer(values, 'amount', 1, 1000000, 'close_accrual.amount'),
        score=number(values, 'score', 0, 1, 'close_accrual.score'),
        in_scope=flag(values, 'in_scope', 'close_accrual.in_scope'),
        reviewed=flag(values, 'reviewed', 'close_accrual.reviewed'),
        refund_instruction=flag(values, 'refund_instruction', 'close_accrual.refund_instruction'),
        has_label=flag(values, 'has_label', 'close_accrual.has_label'),
        authorization_conflict=flag(values, 'authorization_conflict', 'close_accrual.authorization_conflict'),
        arrival=integer(values, 'arrival', 0, 10000000, 'close_accrual.arrival'),
    )


def parse_evidence(values: Mapping[str, Any]) -> ClosingEvidence:
    if not isinstance(values, Mapping):
        raise InvalidRow('close_accrual', 'EXPECTED_OBJECT')
    return ClosingEvidence(
        rma=text(values, 'rma', 'close_accrual.rma'),
        shop=text(values, 'shop', 'close_accrual.shop'),
        amount=integer(values, 'amount', 1, 1000000, 'close_accrual.amount'),
        mismatch=flag(values, 'mismatch', 'close_accrual.mismatch'),
        reviewed=flag(values, 'reviewed', 'close_accrual.reviewed'),
        arrival=integer(values, 'arrival', 0, 10000000, 'close_accrual.arrival'),
        closed=integer(values, 'closed', 0, 10000000, 'close_accrual.closed'),
    )
