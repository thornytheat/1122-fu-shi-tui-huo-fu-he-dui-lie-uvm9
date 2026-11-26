from collections import Counter
import math

import pytest

from returnscope.inspection_score import validate_availability
from returnscope.inspection_score.rolling_validation import clipped_log_loss


def training(count=105):
    records = []
    for day in range(1,count+1):
        records.append({'rma':f'R-{day}','original_shop':'西店','category':'牛仔' if day%2 else '针织','arrival':day,
                        'weight_z':day%9/4,'open_seal':day%2,'repeat_log':day%3/2,'extra_days':0,
                        'found_mismatch':day%9>5,'labeled':day+1})
    return records


def test_rolling_holdout_reports_only_future_verified_labels():
    result = validate_availability(training(),with_labels_before=100,origins=(32,48,66),cal_period=7,lookahead=8)
    assert [row['split'] for row in result]==[32,48,66]
    assert all(point['scored_count']==8 for point in result)
    assert all(point['ready'] for point in result)
    for point in result:
        lo = point['split'] + 7
        assert [row['day'] for row in point['observations']] == list(range(lo,lo+8))
        assert point['training_count']==point['split']-2
        assert point['calibration_count']==6
        assert len({row['fit_id'] for row in point['observations']})==1
        assert math.isfinite(point['calibration_log_loss'])
        assert sum(case['supported'] for case in point['category_reports'])==8


def test_calibration_is_not_assessed_on_late_closing_mixed_days():
    records = training()
    expected = validate_availability(records,with_labels_before=100,origins=(32,),cal_period=10)[0]
    delayed = records[14] | {'rma':'R-late','arrival':30,'labeled':35,'weight_z':99,'found_mismatch':True}
    updated = validate_availability(records + [delayed],with_labels_before=100,origins=(32,),cal_period=10)[0]
    assert expected == updated


def test_output_counts_novelty_without_forcing_probability():
    records = training()
    records[47] |= {'weight_z':30}
    batch = validate_availability(records,with_labels_before=100,origins=(32,),cal_period=10)[0]
    withheld = [row for row in batch['observations'] if row['calibrated_probability'] is None]
    assert len(withheld)==1
    assert withheld[0]['day']==48
    assert withheld[0]['reason']=='FORWARD_PROFILE_NOVEL'
    assert withheld[0]['raw_probability']>.5
    assert withheld[0]['log_loss'] is None
    assert sum(row['referrals'] for row in batch['category_reports'])==1


def test_overlapping_forward_folds_do_not_claim_same_authorization_twice():
    result = validate_availability(training(),with_labels_before=100,origins=(32,36,40),cal_period=5,lookahead=16)
    identities = Counter((row['shop'],row['rma']) for fold in result for row in fold['observations'])
    assert set(identities.values())=={1}
    assert [row['forecast_count'] for row in result]==[16,4,4]


def test_configuration_rejects_negative_and_duplicate_origins():
    for options in ({'origins':(40,39)},{'origins':(40,40)},{'minimum_train':0},{'cal_period':0}):
        with pytest.raises(ValueError,match='INVALID_FORWARD_VALIDATION'):
            validate_availability(training(),with_labels_before=100,**options)


def test_no_history_has_unavailable_losses_and_zero_assessments():
    for row in validate_availability([],with_labels_before=100):
        assert row['training_count']==row['calibration_count']==0
        assert row['calibration_log_loss'] is None and row['raw_log_loss'] is None
        assert row['scored_count']==0 and not row['ready']
        assert row['reason']=='NO_SUPPORTED_FORWARD_OUTCOMES'


def test_log_loss_clips_incorrect_certainty_and_preserves_perfect_scores():
    assert clipped_log_loss(1,True)==clipped_log_loss(0,False)==0
    assert clipped_log_loss(0,True)==clipped_log_loss(1,False)==pytest.approx(12*math.log(10))
    assert clipped_log_loss(.3,False)==pytest.approx(-math.log(.7))
