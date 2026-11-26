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
class ReturnIdentity:
    rma: str
    shop: str
    parcel_key: str
    customer: str
    original_shop: str
    arrival: int
    submitted: int
    weight: int
    seal: bool


def parse(values: Mapping[str, Any]) -> ReturnIdentity:
    if not isinstance(values, Mapping):
        raise InvalidRow('shop_identity', 'EXPECTED_OBJECT')
    rma = text(values, 'rma', 'shop_identity.rma')
    shop = text(values, 'shop', 'shop_identity.shop')
    parcel_key = text(values, 'parcel_key', 'shop_identity.parcel_key')
    customer = text(values, 'customer', 'shop_identity.customer')
    original_shop = text(values, 'original_shop', 'shop_identity.original_shop')
    arrival = integer(values, 'arrival', 0, 10000000, 'shop_identity.arrival')
    submitted = integer(values, 'submitted', 0, 10000000, 'shop_identity.submitted')
    weight = integer(values, 'weight', 1, 90000, 'shop_identity.weight')
    seal = flag(values, 'seal', 'shop_identity.seal')
    return ReturnIdentity(
        rma=rma,
        shop=shop,
        parcel_key=parcel_key,
        customer=customer,
        original_shop=original_shop,
        arrival=arrival,
        submitted=submitted,
        weight=weight,
        seal=seal,
    )
