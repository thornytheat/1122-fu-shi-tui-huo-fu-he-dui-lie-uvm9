from returnscope.delivery import MODULES, application
from returnscope.pipeline import ACCRUAL_MATERIALITY_CENTS, CLOSE, build_accrual_items, run
from returnscope.close_accrual.provisional_ledger import post_journal, stamp_entries


def test_close_accrual_is_the_seventh_workbench_stage():
    assert MODULES[-1] == ('close_accrual', '关账计提')
    snapshot = run()
    assert len(snapshot['stages']) == 7
    assert snapshot['stages'][-1]['title'] == '关账计提'


def test_pipeline_accrual_conserves_every_authorization():
    report = run()['reconciliation']['close_accrual']
    # 没有任何授权单在关账时失去去向。
    assert report['conservation_cents'] == report['requested_cents']
    # 计提 + 实付 + 模型概率折让 = 申请总额。
    assert (report['accrual_cents'] + report['refund_instruction_cents']
            + report['probability_discount_cents']) == report['requested_cents']


def test_only_the_high_exposure_shop_moves_to_provisional_estimate():
    report = run()['reconciliation']['close_accrual']
    assert report['provisional_shops'] == ['浙-南']
    zhenan = next(shop for shop in report['shops'] if shop['shop'] == '浙-南')
    assert zhenan['pending_exposure_cents'] > ACCRUAL_MATERIALITY_CENTS
    assert zhenan['decision'] == 'PROVISIONAL_ESTIMATE'
    assert all(shop['decision'] == 'FINALIZED'
               for shop in report['shops'] if shop['shop'] != '浙-南')


def test_provisional_shop_refund_instructions_are_suspended_not_paid():
    report = run()['reconciliation']['close_accrual']
    suspended = [entry for entry in report['entries'] if entry['instruction_suspended']]
    assert suspended and all(entry['shop'] == '浙-南' for entry in suspended)
    # 暂停的指令整笔进计提，不再按概率折让，也不计入支付。
    assert all(entry['accrual_cents'] == entry['requested_cents'] for entry in suspended)
    paid_shops = {entry['shop'] for entry in report['entries'] if entry['treatment'] == 'PAYMENT_INSTRUCTION'}
    assert '浙-南' not in paid_shops


def test_unreviewed_in_scope_parcels_are_probability_weighted_not_fully_booked():
    report = run()['reconciliation']['close_accrual']
    weighted = [entry for entry in report['entries'] if entry['treatment'] == 'MODEL_EXPECTED_LOSS']
    assert weighted
    assert all(entry['accrual_cents'] < entry['requested_cents'] for entry in weighted)
    assert report['probability_discount_cents'] > 0


def test_missing_label_and_manual_parcels_keep_full_amount():
    report = run()['reconciliation']['close_accrual']
    full = {entry['rma']: entry for entry in report['entries']
            if entry['treatment'] in ('FULL_RESERVE_NO_LABEL', 'MANUAL_FULL_RESERVE')}
    # RMA-0107 无面单，整笔保留。
    assert full['RMA-0107']['treatment'] == 'FULL_RESERVE_NO_LABEL'
    assert full['RMA-0107']['accrual_cents'] == full['RMA-0107']['requested_cents']
    assert all(entry['accrual_cents'] == entry['requested_cents'] for entry in full.values())


def test_next_shift_review_slots_only_cover_unreviewed_pending_parcels():
    report = run()['reconciliation']['close_accrual']
    for shop in report['shops']:
        entries = [entry for entry in report['entries'] if entry['shop'] == shop['shop']]
        expected = sum(not entry['reviewed'] and entry['treatment'] != 'PAYMENT_INSTRUCTION'
                       and not entry['instruction_suspended'] for entry in entries)
        assert shop['next_shift_review_slots'] == expected


def test_pipeline_journal_posting_is_idempotent_at_the_same_cutoff():
    report = run()['reconciliation']['close_accrual']
    first = post_journal(stamp_entries(report))
    second = post_journal(stamp_entries(report), first['ledger'])
    assert second['posted_count'] == 0
    assert len(second['duplicate_entry_ids']) == first['posted_count']
    assert second['ledger_total_cents'] == first['ledger_total_cents']
    # 支付指令不进计提台账。
    assert all(entry['treatment'] != 'PAYMENT_INSTRUCTION' for entry in second['ledger'])


def test_accrual_inputs_are_built_from_register_and_desk_outputs():
    snapshot = run()
    items = build_accrual_items(
        snapshot['reconciliation']['refund_register']['rows'],
        snapshot['stages'][4]['records'],
    )
    assert len(items) == snapshot['metrics']['退货申请']
    assert all(item['arrival'] >= 0 and 0 <= item['score'] <= 1 for item in items)


def test_overview_exposes_close_accrual_and_remains_fingerprint_stable():
    client = application.test_client()
    first = client.get('/api/overview').get_json()
    stage = client.get(f'/api/stages/{MODULES[-1][0]}').get_json()
    assert stage == {**first['stages'][-1], 'run_id': first['run_id']}
    second = client.get('/api/overview').get_json()
    assert first == second
    assert first['metrics']['暂估门店'] == 1
    assert first['metrics']['退款计提(元)'] == first['reconciliation']['close_accrual']['accrual_cents'] // 100


def test_cutoff_constant_matches_the_pipeline_close():
    assert run()['reconciliation']['close_accrual']['cutoff'] == CLOSE
