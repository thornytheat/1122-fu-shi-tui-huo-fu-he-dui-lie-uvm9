from dataclasses import replace
import math

import pytest

from returnscope.return_replay.contracts import RefundEvidence, InvalidRow, parse
from returnscope.return_replay.service import evaluate, validate
from returnscope.return_replay import algorithm

def receipt(name='R1', **changes):
    return dict(rma=name, shop='SX', score=.7, amount=3250, mismatch=True, reviewed=True, arrival=38, closed=42) | changes


def test_no_observed_mismatch_returns_explicit_unavailable_average_precision():  # TRAP-43
    summary = evaluate([receipt(mismatch=False)], as_of=60)['records'][0]
    assert summary['average_precision'] is None
    assert summary['diagnostic'] == 'NO_MISMATCH_OUTCOMES'


def test_average_precision_respects_ties_without_favorable_row_order():
    tied = [receipt('A'), receipt('B', mismatch=False), receipt('C', score=.6)]
    summary = evaluate(tied, as_of=60)['records'][0]
    assert summary['average_precision'] == pytest.approx((.5+2/3)/2)
    assert evaluate(reversed(tied), as_of=60)['records'][0] == summary


def test_pending_inspection_is_not_a_verified_negative():
    rows = [receipt(), receipt('R2', reviewed=False, score=.9)]
    summary = evaluate(rows, as_of=60)['records'][0]
    assert summary['settled'] == summary['observed_mismatches'] == 1
    assert summary['exclusions'] == {'PENDING_INSPECTION': 1}


def test_closed_outcome_is_inclusive_at_as_of():
    summary = evaluate([receipt(closed=61), receipt('R2', closed=60)], as_of=60)['records'][0]
    assert summary['settled'] == 1
    assert summary['exclusions'] == {'CLOSED_OUTSIDE_REPLAY_WINDOW': 1}


def test_conflicting_duplicates_not_double_counted():
    result = evaluate([receipt(), receipt(), receipt('R2'), receipt('R2', mismatch=False)], as_of=60)
    assert result['records'][0]['settled'] == 1
    assert result['records'][0]['exclusions'] == {'OUTCOME_DISAGREEMENT': 1}


def test_threshold_upper_boundary_preserves_possible_savings():
    result = evaluate([receipt()], as_of=60, thresholds=[.7,.71])['records']
    assert result[1]['true_mismatches'] == 1
    assert result[1]['missed_cents'] == 0
    assert result[2]['missed_cents'] == 3250


def test_increasing_threshold_cannot_expand_manual_load():
    items = [receipt('A', score=.5, mismatch=False), receipt('B', score=.9, mismatch=False)]
    totals = [row['manual_load'] for row in evaluate(items, as_of=60)['records'][1:]]
    assert totals == sorted(totals, reverse=True)


def test_invalid_threshold_is_rejected():
    with pytest.raises(ValueError, match='THRESHOLD_OUT_OF_RANGE'):
        evaluate([receipt()], as_of=60, thresholds=(1,))
