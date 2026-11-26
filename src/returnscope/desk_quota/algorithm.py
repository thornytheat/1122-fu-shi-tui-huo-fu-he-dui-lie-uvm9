from __future__ import annotations

from .contracts import ReviewCandidate

from collections import Counter
from dataclasses import asdict


def estimate_reserve(row):
    factor = 1 if not row.in_scope else row.score
    return int(row.amount * factor + .5)


def order_queue(records, reserved_ratio):
    unique = {}
    for row in records:
        key = row.original_shop, row.rma
        if key in unique and unique[key] != row:
            raise ValueError(f'DESK_CONTRADICTORY_AUTHORIZATION:{key}')
        unique[key] = row
    batches = sorted(unique.values(), key=lambda row: (not row.in_scope, row.priority, not row.seal,
                    estimate_reserve(row), -row.arrival), reverse=True)
    ordering = sorted(batches, key=lambda row: (row.original_shop, row.rma))
    ordering.sort(key=lambda row: (not row.in_scope, row.priority, not row.seal,
                  estimate_reserve(row), -row.arrival), reverse=True)
    return ordering, int(len(ordering) * reserved_ratio + .5)


def review_priority(row, threshold):
    if not row.in_scope:
        return 'PARCEL_VERIFICATION'
    if not row.seal:
        return 'UNSEALED'
    if row.priority and row.score >= threshold * .75:
        return 'PRIORITY_CUSTOMER'
    if row.score >= threshold:
        return 'MODEL_RISK'
    return None


def describe(candidate, status, reason, assigned, remaining):
    return asdict(candidate) | {
        'review_reserved_cents': estimate_reserve(candidate) if assigned else 0,
        'state': status,
        'reason': reason,
        'desk_slot': remaining if assigned else None,
    }


def calculate(records, *, capacity=9, threshold=.64, max_per_shop=3):
    if capacity < 1 or max_per_shop < 1 or not 0 < threshold < 1:
        raise ValueError('INVALID_DESK_SETTINGS')
    queue, _ = order_queue(records, 0)
    shop_count = Counter()
    used = 0
    result = []
    for candidate in queue:
        check = review_priority(candidate, threshold)
        if check is None:
            item = describe(candidate, '放行推荐', 'LOW_EXPECTED_LOSS', False, used)
        elif shop_count[candidate.original_shop] >= max_per_shop:
            item = describe(candidate, '人工待处理', 'SHOP_CONCENTRATION', False, used)
        elif used >= capacity:
            item = describe(candidate, '人工待处理', 'DESK_FULL', False, used)
        else:
            used += 1
            shop_count[candidate.original_shop] += 1
            item = describe(candidate, '已派复核', check, True, used)
        result.append(item)
    return result
