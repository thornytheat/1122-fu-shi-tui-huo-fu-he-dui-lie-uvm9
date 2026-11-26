from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .algorithm import build_entries
from .contracts import AccrualItem, ClosingEvidence, InvalidRow, parse_evidence, parse_item


@dataclass(frozen=True, slots=True)
class AccrualRejection:
    line: int
    field: str
    code: str


def validate(items: Iterable[Mapping[str, Any]], evidence: Iterable[Mapping[str, Any]]):
    accepted_items: list[AccrualItem] = []
    rejected_items: list[AccrualRejection] = []
    for line, raw in enumerate(items, 1):
        try:
            accepted_items.append(parse_item(raw))
        except InvalidRow as issue:
            rejected_items.append(AccrualRejection(line, issue.field, issue.code))
    accepted_evidence: list[ClosingEvidence] = []
    rejected_evidence: list[AccrualRejection] = []
    for line, raw in enumerate(evidence, 1):
        try:
            accepted_evidence.append(parse_evidence(raw))
        except InvalidRow as issue:
            rejected_evidence.append(AccrualRejection(line, issue.field, issue.code))
    return accepted_items, accepted_evidence, rejected_items, rejected_evidence


def evaluate(
    items: Iterable[Mapping[str, Any]],
    evidence: Iterable[Mapping[str, Any]] = (),
    *,
    cutoff: int,
    materiality_cents: int,
    locked_shops: Iterable[str] = (),
) -> dict:
    """计算关账退款计提，逐行隔离字段错误，保留原因码和行号。"""
    accepted_items, accepted_evidence, bad_items, bad_evidence = validate(items, evidence)
    outcome = build_entries(
        accepted_items,
        accepted_evidence,
        cutoff=cutoff,
        materiality_cents=materiality_cents,
        locked_shops=frozenset(locked_shops),
    )
    return {
        **outcome,
        'accepted_item_count': len(accepted_items),
        'accepted_evidence_count': len(accepted_evidence),
        'rejected_item_count': len(bad_items),
        'rejected_evidence_count': len(bad_evidence),
        'item_errors': [asdict(error) for error in bad_items],
        'evidence_errors': [asdict(error) for error in bad_evidence],
    }
