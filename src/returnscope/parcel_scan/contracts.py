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
class ParcelScan:
    rma: str
    shop: str
    carrier: str
    label: str
    arrival: int
    observed: int
    weight: int
    seal: bool
    revision: int


def parse(values: Mapping[str, Any]) -> ParcelScan:
    if not isinstance(values, Mapping):
        raise InvalidRow('parcel_scan', 'EXPECTED_OBJECT')
    rma = text(values, 'rma', 'parcel_scan.rma')
    shop = text(values, 'shop', 'parcel_scan.shop')
    carrier = text(values, 'carrier', 'parcel_scan.carrier')
    label = text(values, 'label', 'parcel_scan.label')
    arrival = integer(values, 'arrival', 0, 10000000, 'parcel_scan.arrival')
    observed = integer(values, 'observed', 0, 10000000, 'parcel_scan.observed')
    weight = integer(values, 'weight', 1, 90000, 'parcel_scan.weight')
    seal = flag(values, 'seal', 'parcel_scan.seal')
    revision = integer(values, 'revision', 1, 200, 'parcel_scan.revision')
    return ParcelScan(
        rma=rma,
        shop=shop,
        carrier=carrier,
        label=label,
        arrival=arrival,
        observed=observed,
        weight=weight,
        seal=seal,
        revision=revision,
    )
