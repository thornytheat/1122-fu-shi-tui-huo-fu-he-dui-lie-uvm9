from dataclasses import replace
import math

import pytest

from returnscope.inspection_score.contracts import RiskVector, InvalidRow, parse
from returnscope.inspection_score.service import evaluate, validate
from returnscope.inspection_score import algorithm

def vector(index=4, **changes):
    return dict(rma=f'R{index}', original_shop='SX', category='coat', arrival=index, weight_z=index%8/2,
                open_seal=index%2, repeat_log=index%5/2, extra_days=0,
                found_mismatch=index%7 in (2,4,6), labeled=index+1) | changes


def test_extreme_logistic_remains_finite():  # TRAP-31
    assert algorithm.logistic(10000) == 1
    assert algorithm.logistic(-10000) == 0
    assert algorithm.logistic(0) == .5


def test_calibration_merges_adjacent_inverted_groups():
    blocks = algorithm.calibration_blocks([(.1, False), (.2, True), (.3, False), (.4, True)])
    assert blocks == [(.1,0,1), (.3,1,2), (.4,1,1)]
    assert algorithm.calibrate(.25, blocks) == .5


def test_unfamiliar_weight_profile_does_not_auto_release():  # TRAP-44
    history = [vector(n) for n in range(36)]
    row = evaluate([vector(weight_z=20)], cutoff=41, history=history)['records'][0]
    assert row['score'] is None
    assert row['reason'] == 'WEIGHT_PROFILE_REVIEW'


def test_batch_composition_cannot_change_score():  # TRAP-53
    source = [vector(n) for n in range(36)]
    fixed = evaluate([vector(4)], history=source, cutoff=40)['records'][0]
    batch = evaluate([vector(4), vector(5, weight_z=99)], history=source, cutoff=40)['records'][0]
    assert fixed == batch and fixed['in_scope']


def test_one_class_fit_uses_smoothed_recent_base_rate():
    history = [parse(vector(n, found_mismatch=True)) for n in range(6)]
    model = algorithm.fit_coefficients(history)
    assert model[1] == [0] * 4
    assert algorithm.raw_score(history[0], model) == pytest.approx(7/8)


def test_history_and_hyperparameters_change_version():  # TRAP-54
    source = [vector(n) for n in range(36)]
    fixed = evaluate([vector(4)], history=source, cutoff=40, iterations=120)['records'][0]
    other = evaluate([vector(4)], history=source, cutoff=40, iterations=180)['records'][0]
    assert fixed['fit_id'] != other['fit_id']


def test_repeated_conflicting_closed_label_is_removed():
    evidence = [parse(vector()), parse(vector(found_mismatch=False))]
    assert algorithm.usable_history(evidence, 10) == []


def test_fitting_reduces_log_loss_on_predictive_feature():
    rows = [parse(vector(n, open_seal=n%2, found_mismatch=n%2==1)) for n in range(30)]
    model = algorithm.fit_coefficients(rows)
    assert model[1][1] > 1
    assert sum((algorithm.raw_score(row, model)>=.5) == row.found_mismatch for row in rows) >= 24
