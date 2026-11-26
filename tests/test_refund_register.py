from collections import Counter
from copy import deepcopy
import itertools

import pytest

from returnscope.pipeline import load_counter_statement, run
from returnscope.shop_identity import reconcile_refund_register


def request(name, origin='苏北一店', **changes):
    return {'rma':name,'original_shop':origin,'amount':5500,'seal':True,'priority':False}|changes


def parcel(item, label, **changes):
    return {'original_shop':item['original_shop'],'rma':item['rma'],'valid':True,'reason':'UNIQUE_AUTHORIZATION',
            'seal':True,'alias_labels':[label],'alias_shops':[item['original_shop']]}|changes


def action(item, state='放行推荐', **changes):
    return {'original_shop':item['original_shop'],'rma':item['rma'],'amount':item['amount'],'state':state,
            'in_scope':True,'desk_slot':None,'reason':'LOW_EXPECTED_LOSS'}|changes


def test_finance_cannot_pay_a_refund_without_verified_carrier_linkage():
    first,second = request('RMA-A'),request('RMA-B',amount=3000)
    ledger = reconcile_refund_register([first,second],[parcel(first,'YX:K88')],[action(first),action(second)])
    first_report,second_report=ledger['rows']
    assert first_report['approved_cents']==5500
    assert second_report['approved_cents']==0
    assert first_report['linked_labels']==['YX:K88']
    assert ledger['payment_instructions']==1
    assert ledger['requested_cents']==8500
    assert ledger['payable_cents']==5500
    assert ledger['unreleased_cents']==3000
    assert ledger['reason_totals']=={'VERIFIED_RELEASE_RECOMMENDATION':1,'AUTHORIZATION_WITHOUT_SCAN':1}


def test_duplicate_labels_across_namespaces_hold_each_authorization_once():
    first,second=request('RMA-A'),request('RMA-A','转供库')
    third=request('RMA-A','转供区')
    links=[parcel(first,'YX:11A'),parcel(second,'YX:11A'),parcel(third,'SF:11A')]
    ledger=reconcile_refund_register([first,second,third],links,[action(first),action(second),action(third)])
    assert ledger['contested_carrier_labels']=={'YX:11A':['苏北一店/RMA-A','转供库/RMA-A']}
    assert sum(row['reason']=='CARRIER_LABEL_REUSED' for row in ledger['rows'])==2
    assert ledger['payable_cents']==5500
    assert ledger['unreleased_cents']==11000
    assert ledger['state_totals']=={'人工资料隔离':11000,'可生成退款指令':5500}


def test_review_position_conflict_does_not_unlock_payment():
    first,second=request('A'),request('B')
    refs=[parcel(first,'CX:01'),parcel(second,'CX:02')]
    cases=[action(first,state='已派复核',desk_slot=1,reason='UNSEALED'),
           action(second,state='已派复核',desk_slot=1,reason='WEIGHT_PROFILE')]
    report=reconcile_refund_register([first,second],refs,cases)
    assert report['reason_totals']=={'DUPLICATE_DESK_SLOT':2}
    assert report['contested_review_slots']=={'1':['苏北一店/A','苏北一店/B']}
    assert report['unreleased_cents']==11000
    assert {row['desk_slot'] for row in report['rows']}=={None}


def test_differences_between_approved_and_candidate_refund_amounts_hold_payment():
    primary=request('S1')
    raw=action(primary,amount=500)
    report=reconcile_refund_register([primary],[parcel(primary,'KL:955')],[raw])
    assert report['rows'][0]['reason']=='CANDIDATE_REFUND_DIFFERS'
    assert report['rows'][0]['requested_cents']==5500
    assert report['payable_cents']==0


def test_contested_label_notice_does_not_leak_unrelated_rejected_scans():
    primary=request('S1')
    scans=[{'rma':'S1','reason':'SCAN_REVISION_CONFLICT','valid':False},
           {'rma':'S1','reason':'MALFORMED_LABEL','valid':False},
           {'rma':'S9','reason':'LATE_RECEIPT','valid':False},
           {'rma':'S1','reason':'RECEIVED','valid':True}]
    report=reconcile_refund_register([primary],[],[],scans)
    assert report['rows'][0]['scan_exclusions']==['MALFORMED_LABEL','SCAN_REVISION_CONFLICT']
    assert report['rows'][0]['reason']=='AUTHORIZATION_WITHOUT_SCAN'


def test_alias_conflicts_are_stable_under_permutations():
    first,second,third=request('A'),request('B'),request('C',seal=False)
    links=[parcel(first,'P1'),parcel(second,'P1'),parcel(third,'P2',seal=False)]
    decisions=[action(first),action(second),action(third, in_scope=False)]
    expectation=reconcile_refund_register([first,second,third],links,decisions)
    for sequence in itertools.permutations([first,second,third]):
        assert reconcile_refund_register(sequence,list(reversed(links)),list(reversed(decisions)))==expectation
    assert expectation['payment_instructions']==0


def test_document_conflicts_are_typed_and_preserve_references():
    source=request('F1')
    with pytest.raises(ValueError,match='AUTHORIZATION_CONFLICT:苏北一店/F1'):
        reconcile_refund_register([source,source|{'amount':2}],[],[])
    linked=parcel(source,'K:A1')
    with pytest.raises(ValueError,match='REPEATED_LINKED_CASE:苏北一店/F1'):
        reconcile_refund_register([source],[linked,linked|{'seal':False}],[])
    candidate=action(source)
    with pytest.raises(ValueError,match='CONFLICTING_DESK_ACTION:苏北一店/F1'):
        reconcile_refund_register([source],[linked],[candidate,candidate|{'amount':900}])


def test_unknown_desk_and_carrier_data_are_audited_without_inventing_requests():
    first,unknown=request('S1'),request('SA', '北点')
    report=reconcile_refund_register([first],[parcel(unknown,'DD:88')],[action(unknown)])
    assert report['unknown_links']==['北点/SA']
    assert report['unmatched_actions']==['北点/SA']
    assert report['requested_cents']==5500
    assert report['payment_instructions']==0


def test_manual_exposure_does_not_become_a_payment_instruction():
    primary = request('CASE2')
    facts = [parcel(primary,'TR:198')]
    d = action(primary,in_scope=False,state='已派复核',desk_slot=4,reason='UNRECOGNIZED')
    report = reconcile_refund_register([primary],facts,[d])
    assert report['rows'][0]['desk_slot']==4
    assert report['rows'][0]['state']=='复核中'
    assert report['payment_instructions']==0
    assert report['state_totals']=={'复核中':5500}


@pytest.mark.parametrize('missing', ['action','links','profile','label-collision','amount','seal'])
def test_failing_any_payment_prerequisite_keeps_cents_in_exposure(missing):
    primary = request('A01')
    alias = parcel(primary,'TX:1')
    operation = action(primary)
    records,links,decisions=[primary],[alias],[operation]
    if missing=='action':
        decisions=[]
    elif missing=='links':
        links=[]
    elif missing=='profile':
        decisions=[operation|{'in_scope':False}]
    elif missing=='label-collision':
        duplicate=request('A02')
        records.append(duplicate)
        links.append(parcel(duplicate,'TX:1'))
    elif missing=='amount':
        decisions=[operation|{'amount':100}]
    elif missing=='seal':
        links=[alias|{'seal':False}]
    initial = deepcopy((records,links,decisions))
    ledger = reconcile_refund_register(records,links,decisions)
    assert ledger['payment_instructions']==ledger['payable_cents']==0
    assert ledger['unreleased_cents']==sum(item['amount'] for item in records)
    assert initial==(records,links,decisions)


@pytest.mark.parametrize('capacity',[1,3,7,11,100])
def test_report_conserves_refund_values_at_arbitrary_review_capacities(capacity):
    closed = run(capacity)
    ledger = closed['reconciliation']['refund_register']
    raw = load_counter_statement()['requests']
    assert ledger['requested_cents']==sum(row['amount'] for row in raw)
    assert len(ledger['rows'])==closed['metrics']['退货申请']
    assert sum(ledger['state_totals'].values())==ledger['requested_cents']
    assert ledger['payable_cents']+ledger['unreleased_cents']==ledger['requested_cents']
    assert sum(row['approved_cents'] for row in ledger['rows'])==ledger['payable_cents']
    assert ledger['reason_totals']==dict(Counter(row['reason'] for row in ledger['rows']))
    assert not ledger['contested_review_slots']
    approved=[row for row in ledger['rows'] if row['approved_cents']]
    assert all(row['linked_labels'] and row['desk_slot'] is None for row in approved)
    queue = [row for row in ledger['rows'] if row['desk_slot']]
    assert len(queue)==closed['metrics']['本轮复核']
    assert all(0<row['desk_slot']<=capacity for row in queue)


def test_cross_store_return_alias_never_doubles_financial_liability():
    report=run()['reconciliation']['refund_register']
    rows=[row for row in report['rows'] if '广西-换货店' in row['shop_aliases']]
    assert len(rows)==1
    assert len(rows[0]['shop_aliases'])==2
    assert rows[0]['requested_cents']==load_counter_statement()['requests'][1]['amount']
