from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .algorithm import calculate
from .contracts import RefundEvidence, InvalidRow, parse


@dataclass(frozen=True, slots=True)
class RefundEvidenceRejection:
    line: int
    field: str
    code: str


def validate(rows: Iterable[Mapping[str, Any]]) -> tuple[list[RefundEvidence], list[RefundEvidenceRejection]]:
    accepted = []
    rejected = []
    for line, raw in enumerate(rows, 1):
        try:
            accepted.append(parse(raw))
        except InvalidRow as issue:
            rejected.append(RefundEvidenceRejection(line, issue.field, issue.code))
    return accepted, rejected


def evaluate(rows: Iterable[Mapping[str, Any]], **options) -> dict:
    """计算退货复盘，逐行隔离字段错误，保留原因码和行号。"""
    accepted, rejected = validate(rows)
    outcome = calculate(accepted, **options)
    return {
        'records': outcome,
        'accepted_count': len(accepted),
        'rejected_count': len(rejected),
        'errors': [asdict(error) for error in rejected],
    }


from .store_risk_ledger import reconcile_counter_locations
