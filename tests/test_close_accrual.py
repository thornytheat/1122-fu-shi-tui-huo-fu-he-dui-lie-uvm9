import pytest
from dataclasses import asdict, replace

from returnscope.close_accrual.algorithm import (
    CLEARED_NO_LOSS,
    CONFIRMED_LOSS,
    EVIDENCE_AFTER_CUTOFF,
    EVIDENCE_SHOP_LOCKED,
    FULL_RESERVE_AUTHORIZATION_CONFLICT,
    FULL_RESERVE_NO_LABEL,
    MANUAL_FULL_RESERVE,
    MODEL_EXPECTED_LOSS,
    PAYMENT_INSTRUCTION,
    SUSPENDED_INSTRUCTION,
    build_entries,
    expected_loss_cents,
)
from returnscope.close_accrual.contracts import parse_evidence, parse_item
from returnscope.close_accrual.service import evaluate


def item(name='R1', shop='S1', **changes):
    base = dict(rma=name, shop=shop, amount=10000, score=.4, in_scope=True,
                reviewed=False, refund_instruction=False, has_label=True,
                authorization_conflict=False, arrival=50)
    return parse_item(base | changes)


def evidence(name='R1', shop='S1', **changes):
    base = dict(rma=name, shop=shop, amount=10000, mismatch=True, reviewed=True,
                arrival=50, closed=80)
    return parse_evidence(base | changes)


def treatments(report):
    return {row['rma']: row['treatment'] for row in report['entries']}


def test_refund_instruction_amount_is_not_accrued_again():
    report = build_entries([item(refund_instruction=True)], [], cutoff=140, materiality_cents=10**9)
    row = report['entries'][0]
    assert row['treatment'] == PAYMENT_INSTRUCTION
    assert row['accrual_cents'] == 0
    assert report['accrual_cents'] == 0
    assert report['refund_instruction_cents'] == 10000


def test_unreviewed_in_scope_parcel_uses_model_probability_not_full_amount():
    report = build_entries([item(score=.35)], [], cutoff=140, materiality_cents=10**9)
    row = report['entries'][0]
    assert row['treatment'] == MODEL_EXPECTED_LOSS
    assert row['accrual_cents'] == 3500
    assert row['accrual_cents'] < row['requested_cents']
    assert report['probability_discount_cents'] == 6500


def test_expected_loss_rounds_to_whole_cents():
    assert expected_loss_cents(item(amount=10000, score=.333)) == 3330


def test_out_of_scope_parcel_without_model_probability_is_fully_reserved():
    report = build_entries([item(in_scope=False, score=0.0)], [], cutoff=140, materiality_cents=10**9)
    row = report['entries'][0]
    assert row['treatment'] == MANUAL_FULL_RESERVE
    assert row['accrual_cents'] == 10000


def test_missing_label_keeps_the_full_requested_amount():
    report = build_entries([item(has_label=False)], [], cutoff=140, materiality_cents=10**9)
    assert report['entries'][0]['treatment'] == FULL_RESERVE_NO_LABEL
    assert report['entries'][0]['accrual_cents'] == 10000


def test_authorization_conflict_keeps_the_full_requested_amount():
    report = build_entries([item(authorization_conflict=True, score=.1)], [],
                           cutoff=140, materiality_cents=10**9)
    row = report['entries'][0]
    assert row['treatment'] == FULL_RESERVE_AUTHORIZATION_CONFLICT
    assert row['accrual_cents'] == 10000


def test_closed_evidence_confirms_loss_or_clears_the_authorization():
    loss = build_entries([item()], [evidence(mismatch=True)], cutoff=140, materiality_cents=10**9)
    clear = build_entries([item()], [evidence(mismatch=False)], cutoff=140, materiality_cents=10**9)
    assert loss['entries'][0]['treatment'] == CONFIRMED_LOSS
    assert loss['entries'][0]['accrual_cents'] == 10000
    assert clear['entries'][0]['treatment'] == CLEARED_NO_LOSS
    assert clear['entries'][0]['accrual_cents'] == 0
    # 已结案零计提仍是有去向的授权，守恒不缺项。
    assert clear['conservation_cents'] == clear['requested_cents'] == 10000


def test_shop_over_materiality_defers_to_provisional_estimate():
    rows = [item('A', 'BIG', amount=60000), item('B', 'BIG', amount=50000),
            item('C', 'SMALL', amount=40000)]
    report = build_entries(rows, [], cutoff=140, materiality_cents=100000)
    assert report['provisional_shops'] == ['BIG']
    assert report['finalized_shops'] == ['SMALL']
    big = next(shop for shop in report['shops'] if shop['shop'] == 'BIG')
    assert big['decision'] == 'PROVISIONAL_ESTIMATE'
    assert big['pending_exposure_cents'] == 110000


def test_exposure_equal_to_materiality_still_finalizes_on_time():
    report = build_entries([item(amount=100000)], [], cutoff=140, materiality_cents=100000)
    assert report['provisional_shops'] == []
    assert report['finalized_shops'] == ['S1']


def test_provisional_shop_suspends_refund_instructions_and_reserves_full_amount():
    rows = [item('A', 'P1', amount=60000, refund_instruction=True),
            item('B', 'P1', amount=50000)]
    report = build_entries(rows, [], cutoff=140, materiality_cents=40000)
    suspended, pending = report['entries']
    assert suspended['treatment'] == SUSPENDED_INSTRUCTION
    assert suspended['instruction_suspended'] is True
    assert suspended['accrual_cents'] == 60000
    assert report['refund_instruction_cents'] == 0
    shop = report['shops'][0]
    assert shop['suspended_instructions'] == 1
    # 暂停的指令金额留在计提池，守恒仍闭合。
    assert report['conservation_cents'] == report['requested_cents']


def test_provisional_shop_reserves_next_shift_review_slots():
    rows = [item('A', 'P1', amount=60000, reviewed=True),
            item('B', 'P1', amount=50000, refund_instruction=True),
            item('C', 'P1', amount=40000)]
    report = build_entries(rows, [], cutoff=140, materiality_cents=30000)
    shop = report['shops'][0]
    # 仅未复核且未发指令的包裹占次班复核位：A 已复核、B 已有指令，只有 C。
    assert shop['next_shift_review_slots'] == 1
    assert shop['pending_parcels'] == 2


def test_late_evidence_after_cutoff_is_ignored():
    report = build_entries([item()], [evidence(closed=141)], cutoff=140, materiality_cents=10**9)
    assert report['evidence_exclusions'] == {EVIDENCE_AFTER_CUTOFF: 1}
    assert report['entries'][0]['treatment'] == MODEL_EXPECTED_LOSS
    assert report['entries'][0]['evidence_closed'] is None


def test_late_evidence_cannot_rewrite_a_locked_shop():
    first = build_entries([item()], [evidence()], cutoff=140, materiality_cents=10**9)
    assert first['entries'][0]['treatment'] == CONFIRMED_LOSS
    rerun = build_entries([item()], [evidence(mismatch=False)], cutoff=140,
                          materiality_cents=10**9, locked_shops=frozenset({'S1'}))
    assert rerun['evidence_exclusions'] == {EVIDENCE_SHOP_LOCKED: 1}
    # 锁定门店不再重算，保留原计提口径。
    assert rerun['entries'][0]['treatment'] == MODEL_EXPECTED_LOSS
    assert rerun['shops'][0]['locked'] is True


def test_rerun_at_same_cutoff_is_deterministic():
    rows = [item('A', 'S1'), item('B', 'S2', score=.8)]
    first = build_entries(rows, [evidence('A')], cutoff=140, materiality_cents=5000)
    second = build_entries(list(reversed(rows)), [evidence('A')], cutoff=140, materiality_cents=5000)
    assert first == second


def test_contradictory_duplicate_items_are_rejected():
    with pytest.raises(ValueError, match='ACCRUAL_CONTRADICTORY_AUTHORIZATION:S1/R1'):
        build_entries([item(), item(amount=2)], [], cutoff=140, materiality_cents=10**9)


def test_invalid_settings_raise_explicit_errors():
    with pytest.raises(ValueError, match='INVALID_CUTOFF'):
        build_entries([], [], cutoff=-1, materiality_cents=1)
    with pytest.raises(ValueError, match='INVALID_MATERIALITY'):
        build_entries([], [], cutoff=140, materiality_cents=-1)


def test_service_isolates_bad_rows_without_dropping_valid_ones():
    bad_row = asdict(replace(item('BAD'), amount=0))
    report = evaluate(
        [asdict(item('OK')), bad_row],
        [asdict(evidence('OK')), {'rma': 'E2', 'shop': 'S1', 'amount': 100, 'mismatch': 'yes',
                                  'reviewed': True, 'arrival': 50, 'closed': 80}],
        cutoff=140, materiality_cents=10**9,
    )
    assert report['accepted_item_count'] == 1
    assert report['rejected_item_count'] == 1
    assert report['item_errors'][0]['code'] == 'OUT_OF_RANGE'
    assert report['rejected_evidence_count'] == 1
    assert report['evidence_errors'][0]['field'] == 'close_accrual.mismatch'
    assert {row['rma'] for row in report['entries']} == {'OK'}


def test_contract_rejects_booleans_and_out_of_range_numbers():
    with pytest.raises(ValueError):
        parse_item(dict(rma='R1', shop='S1', amount=10000, score=1.4, in_scope=True,
                        reviewed=False, refund_instruction=False, has_label=True,
                        authorization_conflict=False, arrival=50))
    with pytest.raises(ValueError):
        parse_evidence(dict(rma='R1', shop='S1', amount=10000, mismatch=True,
                            reviewed=True, arrival=50, closed='80'))
