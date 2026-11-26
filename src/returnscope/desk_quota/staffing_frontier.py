from collections import Counter, defaultdict
from math import fsum

from .algorithm import calculate, estimate_reserve, review_priority
from .contracts import parse


def counterparty_load(queue, input_rows, threshold):
    considered = defaultdict(list)
    for row in input_rows:
        considered[row.original_shop].append(row)
    action = {(row['original_shop'],row['rma']):row for row in queue}
    output = []
    for shop,expectations in sorted(considered.items()):
        mandatory = [row for row in expectations if review_priority(row,threshold)]
        assigned = [row for row in mandatory if action[shop,row.rma]['desk_slot'] is not None]
        conflicts = Counter(action[shop,row.rma]['reason'] for row in mandatory if action[shop,row.rma]['desk_slot'] is None)
        output.append({'shop':shop,'eligible':len(mandatory),'slots':len(assigned),'waiting':len(mandatory)-len(assigned),
                       'deferred_causes':dict(conflicts),'uncovered_cents':sum(estimate_reserve(row) for row in mandatory if row not in assigned)})
    return output


def what_if(plan, records, scenario):
    limit,threshold,per_shop = scenario
    by_shop = counterparty_load(plan,records,threshold)
    reserve = sum(row['review_reserved_cents'] for row in plan)
    covered = [row for row in plan if row['desk_slot'] is not None]
    suspended = [row for row in plan if row['state']=='人工待处理']
    clear = [row for row in plan if row['state']=='放行推荐']
    verified = sum(row['amount'] for row in plan)==sum(row.amount for row in records)
    return {'capacity':limit,'threshold':threshold,'shop_limit':per_shop,'assigned':len(covered),'waiting':len(suspended),
            'released':len(clear),'unused_slots':limit-len(covered),'reserved_cents':reserve,
            'exposure_cents':sum(row['uncovered_cents'] for row in by_shop),
            'mandatory_waiting':sum(not row['in_scope'] for row in suspended),
            'release_cost_proxy':round(fsum(row['score']*row['amount'] for row in clear),2),
            'demand_by_shop':by_shop,'payment_reconciled':verified,
            'position_ids':[f"{row['original_shop']}/{row['rma']}" for row in covered]}


def dominated(target, competitor):
    left = (competitor['capacity'],competitor['mandatory_waiting'],competitor['exposure_cents'],competitor['release_cost_proxy'])
    right = (target['capacity'],target['mandatory_waiting'],target['exposure_cents'],target['release_cost_proxy'])
    return left!=right and all(x<=y for x,y in zip(left,right,strict=True))


def mark_frontier(rows):
    for chosen in rows:
        chosen['frontier'] = not any(dominated(chosen,other) for other in rows)
    return rows


def compare_desk_plans(records, *, capacities=(3,6,9), thresholds=(.5,.65,.8), max_per_shop=3):
    capacity_choices = sorted(set(capacities))
    threshold_choices = sorted(set(thresholds))
    if len(capacity_choices)*len(threshold_choices)>80 or not capacity_choices or not threshold_choices:
        raise ValueError('INVALID_SCENARIO_SET')
    if any(type(capacity) is not int or capacity<1 for capacity in capacity_choices) or not all(0<cut<1 for cut in threshold_choices):
        raise ValueError('INVALID_SCENARIO_BOUNDARY')
    requests = [parse(row) for row in records]
    indexed = {}
    for row in requests:
        key = row.original_shop,row.rma
        if key in indexed and indexed[key]!=row:
            raise ValueError('CONFLICTING_STAFFING_REQUEST')
        indexed[key]=row
    unique = list(indexed.values())
    scenarios = []
    for capacity in capacity_choices:
        for threshold in threshold_choices:
            fresh = calculate(unique,capacity=capacity,threshold=threshold,max_per_shop=max_per_shop)
            scenarios.append(what_if(fresh,unique,(capacity,threshold,max_per_shop)))
    return mark_frontier(scenarios)
