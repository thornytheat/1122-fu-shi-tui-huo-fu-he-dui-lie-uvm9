from collections import Counter, defaultdict
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RefundId:
    origin: str
    rma: str

    @property
    def display(self):
        return f'{self.origin}/{self.rma}'


def known_authorizations(request_rows):
    pending = {}
    amounts = {}
    for item in request_rows:
        key = RefundId(item['original_shop'],item['rma'])
        if key in amounts and pending[key] != item:
            raise ValueError(f'AUTHORIZATION_CONFLICT:{key.display}')
        pending[key] = item
        amounts[key] = item['amount']
    return pending


def alias_ledger(authorizations, linked):
    labels = defaultdict(set)
    primary = {}
    unknown = []
    for row in linked:
        identity = RefundId(row['original_shop'],row['rma'])
        if identity not in authorizations:
            unknown.append(identity.display)
            continue
        if identity in primary and primary[identity] != row:
            raise ValueError(f'REPEATED_LINKED_CASE:{identity.display}')
        primary[identity] = row
        for label in row['alias_labels']:
            labels[label].add(identity)
    return primary, labels, sorted(set(unknown))


def determine_status(row, linked, action, contested):
    if contested:
        return '人工资料隔离', 'CARRIER_LABEL_REUSED'
    if linked is None:
        return '人工资料隔离', 'AUTHORIZATION_WITHOUT_SCAN'
    if not linked['valid']:
        return '人工资料隔离', linked['reason']
    if action is None:
        return '人工资料隔离', 'NO_REFUND_DECISION'
    if action['amount'] != row['amount']:
        return '人工资料隔离', 'CANDIDATE_REFUND_DIFFERS'
    if action['state']=='放行推荐' and action['in_scope'] and row['seal'] and linked['seal']:
        return '可生成退款指令', 'VERIFIED_RELEASE_RECOMMENDATION'
    if action['desk_slot'] is not None:
        return '复核中', action['reason']
    return '待人工取证', action['reason']


def reconcile_refund_register(requests, linked, local, scan_rows=()):
    pending = known_authorizations(requests)
    primary,labels,unknown = alias_ledger(pending,linked)
    desk = {}
    duplicate_slots = defaultdict(set)
    for action in local:
        refund = RefundId(action['original_shop'],action['rma'])
        if refund in desk and desk[refund]!=action:
            raise ValueError(f'CONFLICTING_DESK_ACTION:{refund.display}')
        desk[refund] = action
        if action['desk_slot'] is not None:
            duplicate_slots[action['desk_slot']].add(refund)
    reused = {label:entries for label,entries in labels.items() if len(entries)>1}
    label_blocks = {key for conflicts in reused.values() for key in conflicts}
    desk_conflicts = {slot:entries for slot,entries in duplicate_slots.items() if len(entries)>1}
    desk_blocks = {key for conflicts in desk_conflicts.values() for key in conflicts}
    scan_reasons = defaultdict(set)
    for row in scan_rows:
        if not row['valid']:
            scan_reasons[row['rma']].add(row['reason'])
    result = []
    money_by_state = Counter()
    reasons = Counter()
    for identity in sorted(pending,key=lambda item:(item.origin,item.rma)):
        hold = pending[identity]
        link = primary.get(identity)
        action = desk.get(identity)
        state,reason = determine_status(hold,link,action,identity in label_blocks)
        if identity in desk_blocks:
            state,reason = '人工资料隔离','DUPLICATE_DESK_SLOT'
        linked_labels = link['alias_labels'] if link else []
        allocated_slot = action['desk_slot'] if action and state=='复核中' else None
        money_by_state[state] += hold['amount']
        reasons[reason] += 1
        result.append({'rma':identity.rma,'original_shop':identity.origin,'state':state,'reason':reason,
                       'desk_slot':allocated_slot,'approved_cents':hold['amount'] if state=='可生成退款指令' else 0,
                       'requested_cents':hold['amount'],'linked_labels':linked_labels,
                       'scan_exclusions':sorted(scan_reasons[identity.rma]),
                       'shop_aliases':link['alias_shops'] if link else []})
    to_pay = sum(row['approved_cents'] for row in result)
    uncertain = sum(money_by_state.values())-to_pay
    return {'payment_instructions':sum(row['approved_cents']>0 for row in result),'payable_cents':to_pay,'unreleased_cents':uncertain,
            'requested_cents':sum(row['requested_cents'] for row in result),'state_totals':dict(money_by_state),
            'reason_totals':dict(reasons),'rows':result,'unknown_links':unknown,
            'unmatched_actions':sorted(key.display for key in desk.keys()-pending.keys()),
            'contested_carrier_labels':{label:sorted(row.display for row in group) for label,group in sorted(reused.items())},
            'contested_review_slots':{str(slot):sorted(row.display for row in group) for slot,group in sorted(desk_conflicts.items())}}
