from __future__ import annotations

from .contracts import RiskVector

from dataclasses import asdict
from hashlib import sha256
from math import exp, fsum, log, log1p
from statistics import median


def logistic(linear):
    magnitude = exp(-abs(linear))
    return 1 / (1 + magnitude) if linear >= 0 else magnitude / (1 + magnitude)


def inputs(row):
    return row.weight_z, row.open_seal, row.repeat_log, row.extra_days


def usable_history(history, cutoff):
    folded = {}
    conflicts = set()
    for row in history:
        if not row.arrival <= row.labeled < cutoff:
            continue
        key = row.original_shop, row.rma
        if key in folded and folded[key] != row:
            conflicts.add(key)
        folded[key] = row
    return [item for key, item in sorted(folded.items(), key=lambda pair: (pair[1].labeled, pair[0])) if key not in conflicts]


def fit_coefficients(source, learning_rate=.10, iterations=180, regularization=.025):
    vectors = [(inputs(row), int(row.found_mismatch)) for row in source]
    positives = sum(target for _, target in vectors)
    prior = (positives + 1) / (len(source) + 2)
    offset = log(prior) - log1p(-prior)
    weights = [0.0] * 4
    if not 0 < positives < len(source):
        return offset, weights
    for _ in range(iterations):
        errors = [logistic(offset + fsum(a * b for a, b in zip(vector, weights))) - label for vector, label in vectors]
        gradient = [fsum(vector[j] * e for (vector, _), e in zip(vectors, errors)) / len(source)
                    for j in range(len(weights))]
        offset -= learning_rate * fsum(errors) / len(source)
        weights = [weight - learning_rate * (g + regularization * weight) for weight, g in zip(weights, gradient)]
    return offset, weights


def raw_score(row, model):
    offset, weights = model
    return logistic(offset + fsum(value * coef for value, coef in zip(inputs(row), weights)))


def calibration_blocks(scored):
    preliminary = {}
    for score, actual in sorted(scored):
        weighted, count = preliminary.get(score, (0, 0))
        preliminary[score] = weighted + int(actual), count + 1
    blocks = []
    for score, (total, count) in preliminary.items():
        blocks.append((score, total, count))
        while len(blocks) > 1:
            last, prior = blocks[-1], blocks[-2]
            if last[1] * prior[2] >= prior[1] * last[2]:
                break
            blocks[-2:] = [(last[0], last[1] + prior[1], last[2] + prior[2])]
    return blocks


def calibrate(score, blocks):
    for boundary, positives, count in blocks:
        if score <= boundary:
            return (positives + 1) / (count + 2)
    if not blocks:
        return score
    _, positive, count = blocks[-1]
    return (positive + 1) / (count + 2)


def distance_guard(source):
    if not source:
        return [0] * 4
    axes = list(zip(*[inputs(row) for row in source]))
    return [max(values) + max(.5, median(values)) for values in axes]


def calculate(records, *, history, cutoff, iterations=180):
    from .contracts import parse
    if not 1 <= iterations <= 500:
        raise ValueError('INVALID_LOGISTIC_ITERATIONS')
    inventory = usable_history([parse(row) for row in history], cutoff)
    split = (len(inventory) * 3) // 4
    training, calibration = inventory[:split], inventory[split:]
    model = fit_coefficients(training, iterations=iterations)
    signatures = sha256(repr((inventory, cutoff, iterations, 'w4-l2')).encode()).hexdigest()[:16]
    blocks = calibration_blocks((raw_score(row, model), row.found_mismatch) for row in calibration)
    limits = distance_guard(training)
    result = []
    for row in records:
        raw = raw_score(row, model)
        in_scope = len(training) >= 6 and all(value <= max_value for value, max_value in zip(inputs(row), limits))
        result.append(asdict(row) | {
            'raw_score': raw,
            'score': calibrate(raw, blocks) if in_scope else None,
            'in_scope': in_scope,
            'reason': 'CALIBRATED' if in_scope else 'WEIGHT_PROFILE_REVIEW',
            'training_count': len(training),
            'calibration_count': len(calibration),
            'fit_id': signatures,
        })
    return result
