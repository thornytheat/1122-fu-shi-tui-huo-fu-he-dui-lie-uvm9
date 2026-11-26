from collections import Counter, defaultdict
from statistics import median, quantiles


def queue_age_profile(accepted, statement_close):
    delays = sorted(statement_close-row['observed'] for row in accepted)
    return {
        'oldest':max(delays,default=None),
        'median':median(delays) if delays else None,
        'p90':quantiles(delays,n=10,method='inclusive')[-1] if len(delays)>1 else next(iter(delays),None),
    }


def group_information(rows):
    result = defaultdict(list)
    identities = defaultdict(set)
    for row in rows:
        result[row['shop']].append(row)
        if row['valid']:
            identities[row['parcel_key']].add(row['shop'])
    return result, identities


def scan_balance(group):
    safe = [row for row in group if row['valid']]
    problems = [row for row in group if not row['valid']]
    split = Counter(row['reason'] for row in problems)
    updates = sum(row.get('superseded_scans',0) for row in group)
    return safe, problems, split, updates


def summarize_carriers(accepted, labels):
    routes = defaultdict(list)
    for row in accepted:
        routes[row['carrier']].append(row)
    output = []
    for carrier, material in sorted(routes.items()):
        seal_flags = Counter(row['seal'] for row in material)
        distinct = {row['parcel_key'] for row in material}
        recurring = sorted(label for label in distinct if len(labels[label])>1)
        output.append({'carrier':carrier,'packets':len(material),'distinct_labels':len(distinct),
                       'open_seals':seal_flags[False],'aliased_tracking':recurring,
                       'open_seal_rate':seal_flags[False]/len(material),
                       'clock_delay_max':max(row['observed']-row['arrival'] for row in material)})
    return output


def make_alerts(age, rejected, reused, total, *, lag_limit, rejection_rate):
    notices = []
    if age['p90'] is not None and age['p90']>=lag_limit:
        notices.append('BACKLOG_AGE')
    if total and rejected/total>=rejection_rate:
        notices.append('SCAN_REJECT_RATE')
    if reused:
        notices.append('MULTIPLE_STORE_SCAN')
    return notices


def inspect_counter_health(report, *, statement_close, lag_limit=25, rejection_rate=.2):
    if lag_limit<1 or not 0<rejection_rate<=1 or statement_close<=0:
        raise ValueError('INVALID_COUNTER_HEALTH_POLICY')
    grouped, label_owner = group_information(report['records'])
    each_store = []
    for store, evidence in sorted(grouped.items()):
        accepted, rejected, reasons, updates = scan_balance(evidence)
        age = queue_age_profile(accepted,statement_close)
        carriers = summarize_carriers(accepted,label_owner)
        relayed = set().union(*(item['aliased_tracking'] for item in carriers))
        each_store.append({'store':store,'accepted':len(accepted),'rejects':len(rejected),'updated_documents':updates,
                           'scan_total':len(evidence)+updates,'age':age,'carriers':carriers,'reject_reasons':dict(reasons),
                           'alerts':make_alerts(age,len(rejected),relayed,len(evidence),lag_limit=lag_limit,rejection_rate=rejection_rate)})
    raw = sum(store['scan_total'] for store in each_store)+report['rejected_count']
    return {'stores':each_store,'scannable_documents':sum(store['accepted'] for store in each_store),
            'unparseable_documents':report['rejected_count'],'raw_scans':raw,'input_balance':raw==report['accepted_count']+report['rejected_count'],
            'relayed_labels':{key:sorted(shops) for key,shops in sorted(label_owner.items()) if len(shops)>1}}
