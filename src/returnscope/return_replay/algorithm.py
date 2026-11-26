from __future__ import annotations

from .contracts import RefundEvidence

from collections import defaultdict
from math import fsum


def average_precision(outcomes):
    positives = sum(row.mismatch for row in outcomes)
    if not positives:
        return None
    same_score = defaultdict(list)
    for row in outcomes:
        same_score[row.score].append(row)
    detected = inspected = 0
    weighted = []
    for score in sorted(same_score, reverse=True):
        group = same_score[score]
        current_positives = sum(row.mismatch for row in group)
        inspected += len(group)
        detected += current_positives
        weighted.append(current_positives * detected / inspected)
    return fsum(weighted) / positives


def closed_outcomes(records, as_of):
    by_document = defaultdict(set)
    exclusions = defaultdict(int)
    for row in records:
        if not row.reviewed:
            exclusions['PENDING_INSPECTION'] += 1
        elif not row.arrival <= row.closed <= as_of:
            exclusions['CLOSED_OUTSIDE_REPLAY_WINDOW'] += 1
        else:
            by_document[row.shop, row.rma].add(row)
    finished = []
    for key, replaces in sorted(by_document.items()):
        if len(replaces) > 1:
            exclusions['OUTCOME_DISAGREEMENT'] += 1
        else:
            finished.extend(replaces)
    return finished, dict(exclusions)


def compare_operating_points(records, thresholds):
    scorecard = []
    for threshold in thresholds:
        predicted = [row for row in records if row.score >= threshold]
        false_alarms = sum(not row.mismatch for row in predicted)
        missed = [row for row in records if row.score < threshold and row.mismatch]
        scorecard.append({
            'kind': 'threshold',
            'threshold': threshold,
            'request_count': len(predicted),
            'true_mismatches': len(predicted) - false_alarms,
            'manual_load': false_alarms,
            'missed_cents': sum(row.amount for row in missed),
        })
    return scorecard


def calculate(records, *, as_of, thresholds=(.3, .45, .6, .75, .9)):
    if any(not 0 < value < 1 for value in thresholds):
        raise ValueError('THRESHOLD_OUT_OF_RANGE')
    final, exclusions = closed_outcomes(records, as_of)
    false = sum(row.mismatch for row in final)
    return [{
        'kind': 'summary',
        'settled': len(final),
        'observed_mismatches': false,
        'average_precision': average_precision(final),
        'exclusions': exclusions,
        'diagnostic': 'OBSERVED_OUTCOMES_ONLY' if false else 'NO_MISMATCH_OUTCOMES',
    }, *compare_operating_points(final, thresholds)]
