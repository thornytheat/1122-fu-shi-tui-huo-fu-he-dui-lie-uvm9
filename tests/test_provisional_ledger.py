from returnscope.close_accrual.algorithm import (
    MODEL_EXPECTED_LOSS,
    PAYMENT_INSTRUCTION,
    SUSPENDED_INSTRUCTION,
    build_entries,
)
from returnscope.close_accrual.contracts import parse_item
from returnscope.close_accrual.provisional_ledger import entry_id, post_journal, stamp_entries


def item(name='R1', shop='S1', **changes):
    base = dict(rma=name, shop=shop, amount=10000, score=.4, in_scope=True,
                reviewed=False, refund_instruction=False, has_label=True,
                authorization_conflict=False, arrival=50)
    return parse_item(base | changes)


def report(rows, **options):
    settings = dict(cutoff=140, materiality_cents=10**9)
    settings.update(options)
    return build_entries(rows, [], **settings)


def test_entry_id_is_deterministic_for_the_same_cutoff_and_document():
    assert entry_id(140, 'S1', 'R1') == entry_id(140, 'S1', 'R1')
    assert entry_id(140, 'S1', 'R1') != entry_id(141, 'S1', 'R1')
    assert entry_id(140, 'S1', 'R1') != entry_id(140, 'S2', 'R1')
    assert entry_id(140, 'S1', 'R1').startswith('ACR-')


def test_payment_instructions_never_create_journal_entries():
    result = post_journal(report([item(refund_instruction=True)]))
    assert result['posted_count'] == 0
    assert result['ledger'] == []


def test_rerun_at_same_cutoff_does_not_duplicate_entries():
    first = post_journal(report([item('A'), item('B', score=.8)]))
    assert first['posted_count'] == 2
    second = post_journal(report([item('A'), item('B', score=.8)]), first['ledger'])
    assert second['posted_count'] == 0
    assert second['duplicate_count'] == 2
    assert len(second['ledger']) == 2
    # 台账总额在重跑后保持不变。
    assert second['ledger_total_cents'] == first['ledger_total_cents']


def test_suspended_instructions_are_booked_as_full_provisional_reserve():
    rows = [item('A', 'P1', refund_instruction=True), item('B', 'P1')]
    result = post_journal(report(rows, materiality_cents=1))
    treatments = {entry['rma']: entry['treatment'] for entry in result['ledger']}
    assert treatments == {'A': SUSPENDED_INSTRUCTION, 'B': MODEL_EXPECTED_LOSS}
    suspended = next(entry for entry in result['ledger'] if entry['rma'] == 'A')
    assert suspended['accrual_cents'] == 10000
    assert suspended['instruction_suspended'] is True
    assert result['ledger_total_cents'] == 14000


def test_locked_shops_are_recorded_after_posting():
    rows = [item('A', 'LOCKED'), item('B', 'OPEN')]
    result = post_journal(report(rows), ledger=[])
    assert result['locked_shops'] == ['LOCKED', 'OPEN']
    # 已有锁定门店的重跑保留原锁定集合。
    again = post_journal(report(rows), result['ledger'])
    assert again['locked_shops'] == ['LOCKED', 'OPEN']


def test_stamped_entries_are_sorted_and_carry_stable_ids():
    stamped = stamp_entries(report([item('B'), item('A')]))
    assert [row['rma'] for row in stamped['entries']] == ['A', 'B']
    assert all(row['entry_id'] == entry_id(140, row['shop'], row['rma']) for row in stamped['entries'])
    # 支付指令不分配计提分录号也仍然保留在业务证据里。
    paid = stamp_entries(report([item(refund_instruction=True)]))
    assert paid['entries'][0]['treatment'] == PAYMENT_INSTRUCTION
