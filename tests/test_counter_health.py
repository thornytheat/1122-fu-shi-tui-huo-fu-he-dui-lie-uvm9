from collections import Counter

import pytest

from returnscope.parcel_scan import evaluate, inspect_counter_health
from returnscope.pipeline import load_counter_statement, run


def event(rma, location='津南', **changes):
    return {'rma':rma,'shop':location,'label':f'ZH00{rma}','carrier':'SF','arrival':120,'observed':121,'weight':300,
            'seal':True,'revision':1}|changes


def summarize(rows, **options):
    ledger = evaluate(rows,statement_close=150)
    return inspect_counter_health(ledger,statement_close=150,**options)


def test_length_accounting_separates_physical_quality_from_malformed_data():
    samples=[event('A001'),event('A001',revision=2,weight=450),event('A002',observed=151),event('A003',revision=9,weight='坏')]
    output = summarize(samples)
    shop, = output['stores']
    assert output['input_balance']
    assert output['raw_scans']==len(samples)
    assert output['scannable_documents']==1
    assert output['unparseable_documents']==1
    assert shop['scan_total']==3
    assert shop['updated_documents']==1
    assert shop['rejects']==1
    assert shop['reject_reasons']=={'ARRIVED_AFTER_CLOSE':1}
    assert shop['alerts']==['BACKLOG_AGE','SCAN_REJECT_RATE']


def test_relay_tracking_does_not_link_identical_provider_numbers():
    samples=[event('A001',label='ZW0011'),event('A002','静海',label='ZW0011'),event('A003','新港',label='ZW0011',carrier='JD')]
    output = summarize(samples,lag_limit=50)
    assert output['relayed_labels']=={'SF:ZW0011':['津南','静海']}
    early,near,far = output['stores']
    assert early['store']=='新港' and early['alerts']==[]
    assert far['alerts']==near['alerts']==['MULTIPLE_STORE_SCAN']
    assert near['carriers'][0]['aliased_tracking']==['SF:ZW0011']
    assert early['carriers'][0]['aliased_tracking']==[]


def test_rate_and_tail_age_use_own_subset_denominators():
    samples=[event('R01',seal=False),event('R02',arrival=142,observed=145),
             event('R03',arrival=130,observed=149,seal=False),event('R04',arrival=151,observed=151)]
    output = summarize(samples)
    one, = output['stores']
    assert one['age']['oldest']==29 and one['age']['median']==5 and one['age']['p90']==pytest.approx(24.2)
    carrier, = one['carriers']
    assert carrier['open_seals']==2 and carrier['open_seal_rate']==pytest.approx(2/3)
    assert carrier['clock_delay_max']==19
    assert one['alerts']==['SCAN_REJECT_RATE']


def test_all_unscannable_cases_do_not_publish_a_zero_wait_age():
    output = summarize([event('A001',label='无')]); one, = output['stores']
    assert one['age']=={'oldest':None,'median':None,'p90':None}
    assert one['carriers']==[]
    assert one['alerts']==['SCAN_REJECT_RATE']
    assert output['scannable_documents']==0


def test_counter_proof_contains_every_rejected_source_in_fixture():
    proof = run()['reconciliation']['counter_health']
    raw = load_counter_statement()['scans']
    assert proof['input_balance'] and proof['raw_scans']==len(raw)
    assert proof['relayed_labels']
    aggregated = Counter()
    for location in proof['stores']:
        aggregated.update(location['reject_reasons'])
        assert location['scan_total']==location['accepted']+location['rejects']+location['updated_documents']
    assert aggregated['SCAN_REVISION_CONFLICT']==1
    assert aggregated['ARRIVED_AFTER_CLOSE']==1
    assert aggregated['LABEL_UNREADABLE']==1


@pytest.mark.parametrize('overrides',[{'lag_limit':0},{'rejection_rate':0},{'rejection_rate':1.2}])
def test_bad_counter_thresholds_never_replace_live_scan_policy(overrides):
    with pytest.raises(ValueError,match='INVALID_COUNTER_HEALTH_POLICY'):
        summarize([],**overrides)


def test_missing_manifest_makes_empty_but_still_balanced_report():
    result=summarize([])
    assert result['input_balance']
    assert result['raw_scans']==0
    assert result['scannable_documents']==0
    assert result['stores']==[]
    assert result['relayed_labels']=={}


@pytest.mark.parametrize('day, expected', [(112,2),(125,4),(135,4),(140,4)])
def test_carrier_observability_is_recomputed_with_statement_boundary(day, expected):
    samples = [event('FIRST',arrival=100,observed=105),event('SECOND',arrival=100,observed=110),
               event('THIRD',arrival=100,observed=112),event('FOURTH',arrival=100,observed=113)]
    report = evaluate(samples,statement_close=day)
    output = inspect_counter_health(report,statement_close=day)
    assert output['scannable_documents']==expected
    row, = output['stores']
    assert row['age']['oldest']==day-105
    assert row['accepted']+sum(row['reject_reasons'].values())==len(samples)
    assert row['scan_total']==len(samples)


def test_all_shops_are_tied_to_real_scans_but_aliases_keep_names():
    samples = [event('A1','家文店',label='TW0001'),event('A2','万国城',label='TW0001'),event('A3','俞顺',label='TW0001'),
               event('A4','新建',label='TW0002'),event('A5','秋岛',label='TW0002',carrier='WT')]
    report = summarize(samples,lag_limit=80)
    assert report['relayed_labels']=={'SF:TW0001':['万国城','俞顺','家文店']}
    assert sum(len(site['alerts']) for site in report['stores'])==3
    assert report['scannable_documents']==5
    for row in report['stores']:
        assert row['carriers'][0]['packets']==1
        assert row['carriers'][0]['distinct_labels']==1


def test_invalid_stored_reading_cannot_poison_carrier_weightless_reasons():
    samples = [event('Q01', weight=0),event('Q02',observed=99),event('Q03',seal=False),event('Q04',carrier='WT')]
    raw = evaluate(samples,statement_close=150)
    cleaned = inspect_counter_health(raw,lag_limit=100,statement_close=150)
    assert raw['errors']==[{'line':1,'field':'parcel_scan.weight','code':'OUT_OF_RANGE'}]
    assert sum(len(shop['carriers']) for shop in cleaned['stores'])==2
    [store] = cleaned['stores']
    assert store['reject_reasons']=={'STATION_CLOCK_INVALID':1}
    assert store['carriers'][0]['open_seals']==1
    assert cleaned['raw_scans']==len(samples)
    assert cleaned['input_balance']


def test_exact_health_alert_boundary_is_inclusive():
    values = [event('B001',observed=125),event('B002',observed=150)]
    view = summarize(values,lag_limit=25,rejection_rate=.5)
    assert view['stores'][0]['alerts']==['BACKLOG_AGE','SCAN_REJECT_RATE']
    tighter = summarize(values,lag_limit=26,rejection_rate=.51)
    assert tighter['stores'][0]['alerts']==[]


def test_desk_run_health_and_identity_aliases_share_qualified_labels():
    recon=run()['reconciliation']
    relays=set(recon['counter_health']['relayed_labels'])
    authorized=[row for row in recon['refund_register']['rows'] if relays.intersection(row['linked_labels'])]
    assert len(authorized)==1
    assert len(authorized[0]['shop_aliases'])==2
