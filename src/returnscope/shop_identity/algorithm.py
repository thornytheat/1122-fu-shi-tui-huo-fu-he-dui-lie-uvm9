from __future__ import annotations

from .contracts import ReturnIdentity

from collections import defaultdict
from dataclasses import asdict


class ReturnEquivalence:
    def __init__(self, size):
        self.parents = list(range(size))
        self.weights = [1] * size

    def find(self, index):
        while self.parents[index] != index:
            self.parents[index] = self.parents[self.parents[index]]
            index = self.parents[index]
        return index

    def merge(self, left, right):
        a, b = self.find(left), self.find(right)
        if a == b:
            return
        if self.weights[a] < self.weights[b]:
            a, b = b, a
        self.parents[b] = a
        self.weights[a] += self.weights[b]


def components(records):
    groups = ReturnEquivalence(len(records))
    labels = {}
    authorizations = {}
    for key, item in enumerate(records):
        label_match = labels.setdefault(item.parcel_key, key)
        auth_match = authorizations.setdefault((item.customer, item.original_shop, item.rma), key)
        groups.merge(key, label_match)
        groups.merge(key, auth_match)
    folded = defaultdict(list)
    for key, item in enumerate(records):
        folded[groups.find(key)].append(item)
    return folded.values()


def reconcile_component(component):
    sorted_group = sorted(component, key=lambda item: (item.original_shop != item.shop, item.submitted, item.rma,
                                                      item.shop, item.parcel_key, item.weight, item.seal))
    representative = sorted_group[0]
    duplicate_count = len(sorted_group) - 1
    if any(row.customer != representative.customer for row in sorted_group):
        reason = 'PARCEL_OWNER_CONFLICT'
    elif len({(row.original_shop, row.rma) for row in sorted_group}) > 1:
        reason = 'MULTIPLE_REFUND_AUTHORIZATIONS'
    elif duplicate_count:
        reason = 'SWAP_STORE_DUPLICATE'
    else:
        reason = 'UNIQUE_AUTHORIZATION'
    clear = reason in ('SWAP_STORE_DUPLICATE', 'UNIQUE_AUTHORIZATION')
    return asdict(representative) | {
        'reason': reason,
        'valid': clear,
        'duplicate_count': duplicate_count,
        'alias_shops': sorted({row.shop for row in sorted_group}),
        'alias_labels': sorted({row.parcel_key for row in sorted_group}),
    }


def calculate(records):
    output = [reconcile_component(group) for group in components(records)]
    return sorted(output, key=lambda row: (row['original_shop'], row['rma'], row['parcel_key'], row['customer']))
