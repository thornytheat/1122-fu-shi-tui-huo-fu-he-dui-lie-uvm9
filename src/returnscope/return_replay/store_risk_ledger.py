from collections import defaultdict
from math import fsum

from .algorithm import average_precision, closed_outcomes
from .contracts import parse


def error_frequency(rows, threshold):
    categories = defaultdict(int)
    weighted = defaultdict(int)
    scaled = []
    for row in rows:
        predicted = row.score>=threshold
        if row.mismatch:
            result = 'true_review' if predicted else 'undetected_refund'
        else:
            result = 'unnecessary_review' if predicted else 'safe_clear'
        categories[result] += 1
        weighted[result] += row.amount
        scaled.append(row.score-row.mismatch)
    return dict(categories),dict(weighted),scaled


def cost_breakdown(counts, cents, review_cost):
    reviewed = counts.get('true_review',0)+counts.get('unnecessary_review',0)
    labor = reviewed*review_cost
    missed = cents.get('undetected_refund',0)
    exposure = cents.get('true_review',0)+missed
    return {'estimated_labor_cents':labor,'unreviewed_mismatch_cents':missed,'mismatch_amount_cents':exposure,
            'capture_fraction':(exposure-missed)/exposure if exposure else None,'total_loss_proxy_cents':labor+missed}


def reconcile_counter_locations(rows, *, as_of, threshold=.64, review_cost=250):
    if not 0<threshold<1 or type(review_cost) is not int or review_cost<0:
        raise ValueError('INVALID_STORE_REPLAY_COST')
    final,excluded = closed_outcomes([parse(row) for row in rows],as_of)
    sites = defaultdict(list)
    for row in final:
        sites[row.shop].append(row)
    report = []
    for name,observations in sorted(sites.items()):
        counts,cents,errors=error_frequency(observations,threshold)
        count=len(observations)
        estimates=cost_breakdown(counts,cents,review_cost)
        report.append({'store':name,'records':count,'checked_confusion':counts,'amount_confusion':cents,
                       'calibration_bias':fsum(errors)/count,'calibration_brier':fsum(error**2 for error in errors)/count,
                       'average_precision':average_precision(observations),**estimates})
    return {'as_of':as_of,'threshold':threshold,'stores':report,'exclusions':excluded,'closed_cases':len(final),
            'tested_amount_cents':sum(row.amount for row in final),
            'losssum_cents':sum(row['total_loss_proxy_cents'] for row in report)}
