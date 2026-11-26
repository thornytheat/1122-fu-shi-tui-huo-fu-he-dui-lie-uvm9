import pytest

from returnscope.desk_quota import compare_desk_plans
from returnscope.desk_quota.staffing_frontier import dominated


def request(key, shop='南', risk=.75, amount=10000, **extra):
    return {'rma':key,'original_shop':shop,'category':'羽绒','reason':'CALIBRATED','score':risk,'amount':amount,
            'arrival':102,'priority':False,'seal':True,'in_scope':True}|extra


def test_scenario_money_conserved_and_slots_are_unique():
    data = [request('R0',amount=4400),request('R1',shop='西',risk=.53),request('R2',in_scope=False),request('R3',risk=.11)]
    scenarios = compare_desk_plans(data,capacities=[1,2,4],thresholds=[.5,.7],max_per_shop=3)
    assert len(scenarios)==6
    for point in scenarios:
        assert point['payment_reconciled']
        assert point['assigned']+point['waiting']+point['released']==4
        assert point['assigned']+point['unused_slots']==point['capacity']
        assert len(set(point['position_ids']))==point['assigned']
        assert sum(row['slots'] for row in point['demand_by_shop'])==point['assigned']
        assert sum(row['waiting'] for row in point['demand_by_shop'])==point['waiting']
        assert sum(row['uncovered_cents'] for row in point['demand_by_shop'])==point['exposure_cents']


def test_store_concentration_causes_idle_slot_while_risk_waits():
    data = [request('R0',amount=4400),request('R1',amount=4900),request('R2',shop='西',amount=3500)]
    one = compare_desk_plans(data,capacities=[3],thresholds=[.5],max_per_shop=1)[0]
    assert one['assigned']==2 and one['unused_slots']==1
    assert one['waiting']==1
    assert one['reserved_cents']==6300
    south,west = one['demand_by_shop']
    assert south['deferred_causes']=={'SHOP_CONCENTRATION':1}
    assert west['deferred_causes']=={}
    assert south['uncovered_cents']==3300


def test_normalize_the_exposure_of_manual_only_cases_to_full_refund():
    data = [request('R1',risk=.01,amount=6500,in_scope=False),request('R2',risk=.9,amount=8600)]
    point = compare_desk_plans(data,capacities=[1],thresholds=[.5])[0]
    assert point['position_ids']==['南/R1']
    assert point['reserved_cents']==6500
    assert point['exposure_cents']==7740
    assert point['mandatory_waiting']==0


def test_threshold_change_conserves_probability_mass_proxy():
    data = [request('R1',risk=.55,amount=7000),request('R2',risk=.4,amount=8000)]
    first,second = compare_desk_plans(data,capacities=[1],thresholds=[.5,.8])
    assert first['released']==1 and second['released']==2
    assert first['reserved_cents']+first['release_cost_proxy']==second['release_cost_proxy']


def test_empty_counter_prefers_lowest_staffing_requirement():
    results = compare_desk_plans([],capacities=[1,2],thresholds=[.5])
    assert results[0]['frontier'] and not results[1]['frontier']
    assert dominated(results[1],results[0])
    assert not dominated(results[0],results[0])


def test_two_scenarios_with_different_tradeoffs_stay_on_frontier():
    data = [request('R1',risk=.94,amount=4000),request('R2',risk=.89,amount=4000)]
    results = compare_desk_plans(data,capacities=[1,2],thresholds=[.6])
    assert all(row['frontier'] for row in results)
    assert results[0]['exposure_cents']>results[1]['exposure_cents']
    assert not dominated(results[0],results[1])
    assert not dominated(results[1],results[0])


def test_scenarios_reject_invalid_bounds_before_logic():
    for options in ({'capacities':[]},{'capacities':[0]},{'thresholds':[1]},{'thresholds':[]},
                    {'capacities':range(1,51),'thresholds':[.2,.3]}):
        with pytest.raises(ValueError,match='INVALID_SCENARIO'):
            compare_desk_plans([],**options)


def test_duplicate_identical_authorizations_never_add_exposure():
    duplicate = request('R1')
    one = compare_desk_plans([duplicate])
    assert one == compare_desk_plans([duplicate,duplicate])
    with pytest.raises(ValueError,match='CONFLICTING_STAFFING_REQUEST'):
        compare_desk_plans([duplicate,duplicate|{'amount':88}])
