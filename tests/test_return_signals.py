from dataclasses import replace
import math

import pytest

from returnscope.return_signals.contracts import ExpectedPackage, InvalidRow, parse
from returnscope.return_signals.service import evaluate, validate
from returnscope.return_signals import algorithm

def measured(**changes):
    return dict(rma='R1', original_shop='S9', category='coats', arrival=47, submitted=39, weight=400,
                listed_weight=500, prior_returns=1, seal=False, amount=8990, priority=False) | changes


def test_future_weight_does_not_enter_category_statistics():  # TRAP-42
    history = [measured(arrival=day, submitted=2, rma=f'H{day}', weight=490) for day in range(3, 8)]
    future = measured(arrival=9, submitted=4, weight=900, rma='J')
    result = evaluate([measured()], history=history, cutoff=9)
    assert result == evaluate([measured()], history=history + [future], cutoff=9)
    assert result['records'][0]['weight_tolerance'] == .02


def test_exact_weight_variance_uses_instrument_floor():  # TRAP-32
    history = [measured(arrival=day, submitted=0, rma=f'H{day}', weight=500) for day in range(1, 9)]
    assert evaluate([measured()], history=history, cutoff=9)['records'][0]['weight_tolerance'] == .015


def test_no_history_has_explicit_business_prior_tolerance():
    assert evaluate([measured()], history=[], cutoff=5)['records'][0]['weight_tolerance'] == .06


def test_invalid_chronology_is_not_a_zero_day_return():
    evidence = evaluate([measured(submitted=48)], history=[], cutoff=5)['records'][0]
    assert evidence['reason'] == 'AUTHORIZATION_AFTER_RECEIPT'
    assert evidence['valid'] is False


def test_elapsed_days_at_return_deadline():
    rows = evaluate([measured(arrival=53), measured(arrival=54)], history=[], cutoff=5)['records']
    assert rows[0]['outside_policy'] is False
    assert rows[1]['outside_policy'] is True
    assert rows[1]['features'][3] == pytest.approx(1 / 14)


def test_invalid_listed_weight_cannot_be_divisor():
    result = evaluate([measured(listed_weight=0), measured()], history=[], cutoff=5)
    assert result['rejected_count'] == 1
    assert len(result['records']) == 1


def test_limit_prevents_one_broken_scale_from_domination():
    row = evaluate([measured(weight=85000)], history=[], cutoff=5)['records'][0]
    assert row['features'][0] == 20
    assert row['delta_ratio'] == 169


def test_repeat_refund_authorization_counts_once_in_history():
    history = [measured(arrival=4, submitted=1, weight=480), measured(arrival=5, submitted=1, weight=450)]
    assert len(algorithm.fitting_rows([parse(value) for value in history], 10)) == 1
