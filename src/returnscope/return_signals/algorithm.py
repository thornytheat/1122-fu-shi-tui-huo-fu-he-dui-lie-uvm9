from __future__ import annotations

from .contracts import ExpectedPackage

from collections import defaultdict
from statistics import median
from dataclasses import asdict
from math import log1p


def package_delta(measured, expected):
    return abs(measured - expected) / expected


def fitting_rows(rows, cutoff):
    eligible = sorted([row for row in rows if row.arrival < cutoff and row.submitted <= row.arrival],
                      key=lambda row: (row.arrival, row.original_shop, row.rma))
    seen = set()
    unique = []
    for row in eligible:
        identity = row.original_shop, row.rma
        if identity in seen:
            continue
        unique.append(row)
        seen.add(identity)
    return unique


def fit_variance(history, cutoff, minimum_group):
    category_offsets = defaultdict(list)
    for row in fitting_rows(history, cutoff):
        category_offsets[row.category].append(package_delta(row.weight, row.listed_weight))
    global_deltas = [value for group in category_offsets.values() for value in group]
    return {
        'overall': max(.015, median(global_deltas)) if global_deltas else .06,
        'by_category': {key: max(.015, median(values)) for key, values in category_offsets.items()
                        if len(values) >= minimum_group},
    }


def feature_record(row, tolerances, maximum_days):
    delta = package_delta(row.weight, row.listed_weight)
    elapsed = row.arrival - row.submitted
    reference = tolerances['by_category'].get(row.category, tolerances['overall'])
    x = [min(20, delta / reference), 0 if row.seal else 1,
         log1p(row.prior_returns), max(0, elapsed - maximum_days) / maximum_days]
    return asdict(row) | {
        'features': x,
        'delta_ratio': delta,
        'weight_tolerance': reference,
        'elapsed_days': elapsed,
        'outside_policy': elapsed > maximum_days,
        'valid': elapsed >= 0,
        'reason': 'FEATURES_READY' if elapsed >= 0 else 'AUTHORIZATION_AFTER_RECEIPT',
    }


def calculate(records, *, history, cutoff, minimum_group=5, maximum_days=14):
    from .contracts import parse
    if maximum_days < 1 or minimum_group < 1:
        raise ValueError('INVALID_RETURN_FEATURE_POLICY')
    tolerances = fit_variance([parse(row) for row in history], cutoff, minimum_group)
    return [feature_record(row, tolerances, maximum_days) for row in records]
