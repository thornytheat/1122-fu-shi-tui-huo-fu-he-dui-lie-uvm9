from __future__ import annotations

from collections import Counter, defaultdict

from .contracts import AccrualItem, ClosingEvidence


# 已生成退款指令的金额进入支付，不再计提。
PAYMENT_INSTRUCTION = 'PAYMENT_INSTRUCTION'
# 无面单或授权冲突，资料不足，申请金额整笔保留。
FULL_RESERVE_NO_LABEL = 'FULL_RESERVE_NO_LABEL'
FULL_RESERVE_AUTHORIZATION_CONFLICT = 'FULL_RESERVE_AUTHORIZATION_CONFLICT'
# 结案证据已定案：复核确认错件按申请金额全提，复核排除错件则零计提。
CONFIRMED_LOSS = 'CONFIRMED_LOSS'
CLEARED_NO_LOSS = 'CLEARED_NO_LOSS'
# 未完成复核：模型在域内按概率折算预计损失，域外无法自动评分，整笔保留。
MODEL_EXPECTED_LOSS = 'MODEL_EXPECTED_LOSS'
MANUAL_FULL_RESERVE = 'MANUAL_FULL_RESERVE'
# 暂估门店里本可发出的退款指令暂停，转入计提池，整笔暂估。
SUSPENDED_INSTRUCTION = 'SUSPENDED_INSTRUCTION'

FULL_RESERVE_TREATMENTS = frozenset((
    FULL_RESERVE_NO_LABEL,
    FULL_RESERVE_AUTHORIZATION_CONFLICT,
    MANUAL_FULL_RESERVE,
    CONFIRMED_LOSS,
    SUSPENDED_INSTRUCTION,
))

# 晚到结案证据的排除原因。
EVIDENCE_AFTER_CUTOFF = 'EVIDENCE_AFTER_CUTOFF'
EVIDENCE_SHOP_LOCKED = 'EVIDENCE_SHOP_LOCKED'
EVIDENCE_PENDING_INSPECTION = 'EVIDENCE_PENDING_INSPECTION'
EVIDENCE_DUPLICATE = 'EVIDENCE_DUPLICATE'


def expected_loss_cents(item: AccrualItem) -> int:
    """模型概率折算的预计损失，四舍五入到分；域外物件不享受概率折让。"""
    if not item.in_scope:
        return item.amount
    return int(item.amount * item.score + 0.5)


def classify(item: AccrualItem, evidence: ClosingEvidence | None, *, instruction_suspended: bool) -> dict:
    suspended = bool(instruction_suspended and item.refund_instruction)
    if item.refund_instruction and not instruction_suspended:
        treatment, accrual = PAYMENT_INSTRUCTION, 0
    elif suspended:
        # 暂估门店的退款指令暂停发出，金额整笔转入暂估，不再享受概率折让。
        treatment, accrual = SUSPENDED_INSTRUCTION, item.amount
    elif not item.has_label:
        treatment, accrual = FULL_RESERVE_NO_LABEL, item.amount
    elif item.authorization_conflict:
        treatment, accrual = FULL_RESERVE_AUTHORIZATION_CONFLICT, item.amount
    elif evidence is not None and evidence.reviewed and evidence.mismatch:
        treatment, accrual = CONFIRMED_LOSS, item.amount
    elif evidence is not None and evidence.reviewed and not evidence.mismatch:
        treatment, accrual = CLEARED_NO_LOSS, 0
    elif not item.in_scope:
        treatment, accrual = MANUAL_FULL_RESERVE, item.amount
    else:
        treatment, accrual = MODEL_EXPECTED_LOSS, expected_loss_cents(item)
    return {
        'rma': item.rma,
        'shop': item.shop,
        'requested_cents': item.amount,
        'score': item.score,
        'in_scope': item.in_scope,
        'reviewed': item.reviewed,
        'accrual_cents': accrual,
        'treatment': treatment,
        'instruction_suspended': suspended,
        'evidence_closed': evidence.closed if evidence is not None else None,
    }


def pending_exposure_cents(items: list[AccrualItem]) -> int:
    """待复核敞口：退款指令尚未生成、需要关账判断的申请金额合计。"""
    return sum(item.amount for item in items if not item.refund_instruction)


def select_provisional_shops(items: list[AccrualItem], materiality_cents: int) -> set[str]:
    """敞口超过计提重要性的门店延后定稿、转暂估。"""
    exposure: dict[str, int] = defaultdict(int)
    for item in items:
        if not item.refund_instruction:
            exposure[item.shop] += item.amount
    return {shop for shop, total in exposure.items() if total > materiality_cents}


def filter_evidence(evidence: list[ClosingEvidence], *, cutoff: int, locked_shops: set[str]):
    usable: dict[tuple[str, str], ClosingEvidence] = {}
    exclusions = Counter()
    for row in evidence:
        if not row.arrival <= row.closed <= cutoff:
            exclusions[EVIDENCE_AFTER_CUTOFF] += 1
            continue
        if not row.reviewed:
            exclusions[EVIDENCE_PENDING_INSPECTION] += 1
            continue
        if row.shop in locked_shops:
            # 已定稿门店的晚到结案记录不能改写历史计提。
            exclusions[EVIDENCE_SHOP_LOCKED] += 1
            continue
        key = (row.shop, row.rma)
        if key in usable and usable[key] != row:
            exclusions[EVIDENCE_DUPLICATE] += 1
            continue
        usable[key] = row
    return usable, dict(exclusions)


def build_entries(
    items: list[AccrualItem],
    evidence: list[ClosingEvidence],
    *,
    cutoff: int,
    materiality_cents: int,
    locked_shops: frozenset[str] = frozenset(),
) -> dict:
    if type(cutoff) is not int or cutoff < 0:
        raise ValueError('INVALID_CUTOFF')
    if type(materiality_cents) is not int or materiality_cents < 0:
        raise ValueError('INVALID_MATERIALITY')
    indexed: dict[tuple[str, str], AccrualItem] = {}
    for item in items:
        key = (item.shop, item.rma)
        if key in indexed and indexed[key] != item:
            raise ValueError(f'ACCRUAL_CONTRADICTORY_AUTHORIZATION:{item.shop}/{item.rma}')
        indexed[key] = item
    usable_evidence, evidence_exclusions = filter_evidence(
        evidence, cutoff=cutoff, locked_shops=set(locked_shops),
    )
    provisional = select_provisional_shops(list(indexed.values()), materiality_cents)
    provisional -= set(locked_shops)
    entries = []
    per_shop_items: dict[str, list[AccrualItem]] = defaultdict(list)
    for (shop, rma), item in sorted(indexed.items()):
        per_shop_items[shop].append(item)
        matched = usable_evidence.get((shop, rma))
        entry = classify(item, matched, instruction_suspended=shop in provisional)
        entries.append(entry)
    shops = []
    for shop in sorted(per_shop_items):
        shop_entries = [entry for entry in entries if entry['shop'] == shop]
        pending = [indexed[shop, entry['rma']] for entry in shop_entries
                   if not indexed[shop, entry['rma']].refund_instruction]
        decision = 'PROVISIONAL_ESTIMATE' if shop in provisional else 'FINALIZED'
        shops.append({
            'shop': shop,
            'decision': decision,
            'locked': shop in locked_shops,
            'pending_exposure_cents': sum(item.amount for item in pending),
            'pending_parcels': len(pending),
            'next_shift_review_slots': sum(
                not item.reviewed and not item.refund_instruction for item in pending
            ),
            'suspended_instructions': sum(entry['instruction_suspended'] for entry in shop_entries),
            'accrual_cents': sum(entry['accrual_cents'] for entry in shop_entries),
        })
    totals = Counter()
    for entry in entries:
        totals[entry['treatment']] += entry['accrual_cents']
    requested = sum(item.amount for item in indexed.values())
    # 暂估门店的退款指令已暂停发出，其金额留在计提池，不计入已支付。
    paid = sum(
        entry['requested_cents'] for entry in entries
        if entry['treatment'] == PAYMENT_INSTRUCTION and not entry['instruction_suspended']
    )
    accrual = sum(entry['accrual_cents'] for entry in entries)
    # 概率折让额：模型域内未复核件按概率折算，申请额与计提额的差额可追溯。
    discount = sum(
        entry['requested_cents'] - entry['accrual_cents']
        for entry in entries if entry['treatment'] == MODEL_EXPECTED_LOSS
    )
    # 守恒：支付、全额保留、概率折让件与已结案零计提件的申请额合计必须等于
    # 全部申请额，即没有任何授权单在关账时被遗漏。
    accounted_treatments = FULL_RESERVE_TREATMENTS | frozenset((PAYMENT_INSTRUCTION, MODEL_EXPECTED_LOSS, CLEARED_NO_LOSS))
    conservation = sum(
        entry['requested_cents'] for entry in entries if entry['treatment'] in accounted_treatments
    )
    return {
        'cutoff': cutoff,
        'materiality_cents': materiality_cents,
        'provisional_shops': sorted(provisional),
        'finalized_shops': sorted(shop for shop in per_shop_items if shop not in provisional),
        'locked_shops': sorted(locked_shops),
        'entries': entries,
        'shops': shops,
        'treatment_totals_cents': dict(totals),
        'requested_cents': requested,
        'refund_instruction_cents': paid,
        'accrual_cents': accrual,
        'probability_discount_cents': discount,
        'conservation_cents': conservation,
        'suspended_instruction_cents': sum(
            entry['requested_cents'] for entry in entries if entry['instruction_suspended']
        ),
        'evidence_exclusions': evidence_exclusions,
    }
