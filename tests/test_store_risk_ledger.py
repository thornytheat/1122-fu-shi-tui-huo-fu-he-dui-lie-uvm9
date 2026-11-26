import pytest
from returnscope.return_replay import reconcile_counter_locations
from returnscope.pipeline import load_counter_statement, run


def receipt(name, **changes):
    return {'rma':name,'shop':'NW1','score':.7,'amount':1000,'mismatch':True,'reviewed':True,'arrival':70,'closed':77}|changes


def test_claims_and_review_cost_are_additive_on_verified_counters():
    items = [receipt('R1',amount=2400),receipt('R2',amount=2800,score=.2),
             receipt('R3',shop='NW2',amount=5100,mismatch=False),receipt('R4',shop='NW2',reviewed=False)]
    view = reconcile_counter_locations(items,as_of=80)
    assert view['exclusions']=={'PENDING_INSPECTION':1}
    assert view['tested_amount_cents']==10300
    first,second=view['stores']
    assert first['unreviewed_mismatch_cents']==2800
    assert first['capture_fraction']==pytest.approx(2400/5200)
    assert first['estimated_labor_cents']==250
    assert first['checked_confusion']=={'true_review':1,'undetected_refund':1}
    assert second['capture_fraction'] is None and second['average_precision'] is None
    assert second['calibration_brier']==pytest.approx(.49)
    assert view['losssum_cents']==3300


def test_unknown_shop_never_creates_a_zero_value_ledger():
    report = reconcile_counter_locations([receipt('R1',closed=81)],as_of=80)
    assert report['stores']==[]
    assert report['closed_cases']==0
    assert report['exclusions']=={'CLOSED_OUTSIDE_REPLAY_WINDOW':1}


def test_inconsistent_versions_quarantine_only_the_contested_rma():
    entries=[receipt('R1'),receipt('R1',amount=4900),receipt('R2',shop='NW2')]
    report = reconcile_counter_locations(entries,as_of=80)
    assert report['closed_cases']==1
    assert report['exclusions']=={'OUTCOME_DISAGREEMENT':1}
    assert [row['store'] for row in report['stores']]==['NW2']


@pytest.mark.parametrize('capacity',[1,5,9,100])
def test_full_counter_review_reconciliation_stays_consistent(capacity):
    report = run(capacity)
    reconciliation = report['reconciliation']
    raw = load_counter_statement()
    assert report['metrics']['退货申请']==len(raw['requests'])
    assert report['metrics']['本轮复核']<=capacity
    assert sum(row['status']=='已派复核' for row in report['rows'])==report['metrics']['本轮复核']
    assert reconciliation['location_review']['closed_cases']==report['stages'][5]['records'][0]['settled']
    assert reconciliation['location_review']['exclusions']==report['stages'][5]['records'][0]['exclusions']
    assert sum(row['records'] for row in reconciliation['location_review']['stores'])==reconciliation['location_review']['closed_cases']
    assert all(row['payment_reconciled'] for row in reconciliation['staffing_frontier'])


def test_scenario_reports_fixed_count_after_adjusting_staffing():
    first,second = run(1),run(12)
    for independent in ('location_review','staffing_frontier','rolling_validation'):
        assert first['reconciliation'][independent]==second['reconciliation'][independent]
    assert first['reconciliation']['refund_register']['rows'] != second['reconciliation']['refund_register']['rows']
    assert first['metrics']['本轮复核']<second['metrics']['本轮复核']


def test_invalid_review_cost_is_error_not_an_improved_value():
    for settings in ({'threshold':1},{'review_cost':-1},{'review_cost':.25}):
        with pytest.raises(ValueError,match='INVALID_STORE_REPLAY_COST'):
            reconcile_counter_locations([],as_of=80,**settings)
