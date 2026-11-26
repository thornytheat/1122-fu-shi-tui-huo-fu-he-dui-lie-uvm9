from dataclasses import replace
import math

import pytest

from returnscope.desk_quota.contracts import ReviewCandidate, InvalidRow, parse
from returnscope.desk_quota.service import evaluate, validate
from returnscope.desk_quota import algorithm

def candidate(name='R1', **changes):
    return dict(rma=name, original_shop='SX', category='coat', reason='CALIBRATED', score=.72,
                in_scope=True, amount=8999, arrival=96, priority=False, seal=True) | changes


def test_receipt_risk_takes_customer_cost_into_account():
    rows = evaluate([candidate(), candidate('R2', amount=12000, score=.7)], capacity=1)['records']
    assert rows[0]['rma'] == 'R2'
    assert rows[1]['reason'] == 'DESK_FULL'


def test_manual_mandate_precedes_high_scoring_known_item():  # TRAP-19
    profile = candidate('R2', score=0, amount=50, in_scope=False)
    result = evaluate([candidate(), profile], capacity=1)['records']
    assert result[0]['rma'] == 'R2'
    assert result[0]['reason'] == 'PARCEL_VERIFICATION'
    assert result[1]['reason'] == 'DESK_FULL'


def test_saturation_at_one_shop_does_not_block_next_shop():
    rows = [candidate(), candidate('R2'), candidate('R3', original_shop='SY')]
    result = evaluate(rows, capacity=3, max_per_shop=1)['records']
    assert [row['reason'] for row in result] == ['MODEL_RISK', 'SHOP_CONCENTRATION', 'MODEL_RISK']


def test_breaking_seal_demands_desk_even_at_zero_model_risk():
    item = evaluate([candidate(score=0, seal=False)])['records'][0]
    assert item['reason'] == 'UNSEALED'


def test_below_threshold_is_clear_with_zero_reserve():
    item = evaluate([candidate(score=.42)])['records'][0]
    assert item['state'] == '放行推荐'
    assert item['review_reserved_cents'] == 0


def test_priority_needs_three_quarters_of_base_threshold():
    item = evaluate([candidate(score=.48, priority=True)])['records'][0]
    assert item['reason'] == 'PRIORITY_CUSTOMER'


def test_equivalent_candidates_do_not_consume_two_slots():
    rows = evaluate([candidate(), candidate()], capacity=1)['records']
    assert len(rows) == 1 and rows[0]['desk_slot'] == 1


def test_conflicting_payment_documents_are_blocked():
    with pytest.raises(ValueError, match='DESK_CONTRADICTORY_AUTHORIZATION'):
        evaluate([candidate(), candidate(amount=10)])
