from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from . import close_accrual, desk_quota, inspection_score, parcel_scan, return_replay, return_signals, shop_identity


DEFAULT_CAPACITY = 9
CLOSE = 140
MODEL_CUTOFF = 102
# 计提重要性：门店待复核敞口（待复核申请毛额）超过该金额（分）即延后定稿、转暂估。
# 取值介于浙-南（187,960 分）与粤-西（185,370 分）敞口之间，使高敞口门店进入暂估。
ACCRUAL_MATERIALITY_CENTS = 186000

# 授权冲突类原因：面单复用、复核位冲突、候选金额差异，均须整笔保留。
_AUTHORIZATION_CONFLICT_REASONS = frozenset((
    'CARRIER_LABEL_REUSED',
    'DUPLICATE_DESK_SLOT',
    'CANDIDATE_REFUND_DIFFERS',
))


def load_counter_statement():
    journal = Path(__file__).resolve().parents[2] / 'sample_data' / 'western_region_return_counter.json'
    return json.loads(journal.read_text(encoding='utf-8'))


def join_identity(accepted_scans, requests):
    declared = {row['rma']: row for row in requests}
    unmatched = []
    qualified = []
    for scan in accepted_scans:
        declaration = declared.get(scan['rma'])
        if declaration:
            qualified.append(declaration | scan)
        else:
            unmatched.append({'rma': scan['rma'], 'reason': 'NO_DECLARED_AUTHORIZATION'})
    return qualified, unmatched


def prepare_score_inputs(feature_rows):
    scored = []
    for record in feature_rows:
        if record['valid']:
            weight, seal, repeat, lateness = record['features']
            scored.append(record | {'weight_z': weight, 'open_seal': seal, 'repeat_log': repeat, 'extra_days': lateness,
                                    'found_mismatch': False, 'labeled': 0})
    return scored


def compute_rows(declared, identities, scans, desk):
    decisions = {item['rma']: item for item in desk}
    reason = {item['rma']: item['reason'] for item in scans if not item['valid']}
    reason.update({item['rma']: item['reason'] for item in identities if not item['valid']})
    result = []
    for authorization in declared:
        rma = authorization['rma']
        action = decisions.get(rma)
        confidence = action['score'] if action and action['in_scope'] else None
        result.append({
            'rma': rma,
            'shop': authorization['original_shop'],
            'category': authorization['category'],
            'refund': round(authorization['amount'] / 100, 2),
            'confidence': round(confidence, 3) if confidence is not None else None,
            'place': action['desk_slot'] if action else None,
            'status': action['state'] if action else '资料隔离',
            'reason': action['reason'] if action else reason.get(rma, 'MISSING_INSPECTABLE_PARCEL'),
        })
    return sorted(result, key=lambda row: (row['place'] is None, row['place'] or 0, row['shop'], row['rma']))


def build_accrual_items(register_rows, desk_rows):
    """把退款台账与复核配额结果转换为关账计提输入。"""
    desk = {(row['original_shop'], row['rma']): row for row in desk_rows}
    items = []
    for row in register_rows:
        key = (row['original_shop'], row['rma'])
        quota = desk.get(key)
        reason = row['reason']
        items.append({
            'rma': row['rma'],
            'shop': row['original_shop'],
            'amount': row['requested_cents'],
            'score': quota['score'] if quota is not None else 0.0,
            'in_scope': bool(quota and quota['in_scope']),
            'reviewed': False,
            'refund_instruction': row['approved_cents'] > 0,
            'has_label': reason != 'AUTHORIZATION_WITHOUT_SCAN',
            'authorization_conflict': reason in _AUTHORIZATION_CONFLICT_REASONS,
            'arrival': quota['arrival'] if quota is not None else 0,
        })
    return items


def run(capacity: int | None = None) -> dict:
    source = load_counter_statement()
    scans = parcel_scan.evaluate(source['scans'], statement_close=CLOSE)
    valid_scans = [row for row in scans['records'] if row['valid']]
    authorizations, unmatched = join_identity(valid_scans, source['requests'])
    linked = shop_identity.evaluate(authorizations)
    candidates = {row['rma']: row for row in source['requests']}
    merged = [candidates[row['rma']] | row for row in linked['records'] if row['valid']]
    features = return_signals.evaluate(merged, history=source['history'], cutoff=MODEL_CUTOFF)
    serving_rows = prepare_score_inputs(features['records'])
    scores = inspection_score.evaluate(serving_rows, history=source['learned'], cutoff=MODEL_CUTOFF)
    features_by_rma = {row['rma']: row for row in serving_rows}
    requests = [features_by_rma[entry['rma']] | entry | {'score': entry['score'] or 0} for entry in scores['records']]
    desk = desk_quota.evaluate(requests, capacity=capacity if capacity is not None else DEFAULT_CAPACITY)
    replay = return_replay.evaluate(source['settled'], as_of=CLOSE)
    register = shop_identity.reconcile_refund_register(
        source['requests'], linked['records'], desk['records'], scans['records'],
    )
    accrual_items = build_accrual_items(register['rows'], desk['records'])
    accrual = close_accrual.evaluate(
        accrual_items,
        source['settled'],
        cutoff=CLOSE,
        materiality_cents=ACCRUAL_MATERIALITY_CENTS,
    )
    rows = compute_rows(source['requests'], linked['records'], scans['records'], desk['records'])
    states = Counter(row['status'] for row in rows)
    summaries = [
        ('验包流水', f'收到 {len(valid_scans)} 笔可检面单，另记录撤回与异常', scans),
        ('换店去重', f"归并到 {len(linked['records'])} 个授权", linked),
        ('退货特征', '只以结算前历史估计商品称重误差', features),
        ('验包评分', '历史按结算顺序切为训练和校准两段', scores),
        ('复核配额', f"已派件 {states['已派复核']} 单，门店集中度受限", desk),
        ('退货复盘', f"仅复核 {replay['records'][0]['settled']} 单已结单据", replay),
        ('关账计提', (
            f"本期计提 {accrual['accrual_cents'] // 100} 元，"
            f"{len(accrual['provisional_shops'])} 家门店转暂估"
        ), {'records': accrual['entries'], 'errors': accrual['item_errors']}),
    ]
    return {
        'reconciliation': {
            'counter_health': parcel_scan.inspect_counter_health(scans,statement_close=CLOSE),
            'refund_register': register,
            'rolling_validation': inspection_score.validate_availability(source['learned'], with_labels_before=MODEL_CUTOFF),
            'staffing_frontier': desk_quota.compare_desk_plans(requests),
            'location_review': return_replay.reconcile_counter_locations(source['settled'],as_of=CLOSE),
            'close_accrual': accrual,
        },
        'metrics': {'退货申请': len(rows), '可放行': states['放行推荐'], '本轮复核': states['已派复核'],
                    '人工待处理': states['人工待处理'] + states['资料隔离'],
                    '退款计提(元)': accrual['accrual_cents'] // 100,
                    '暂估门店': len(accrual['provisional_shops'])},
        'columns': {'rma': '申请编号', 'shop': '原门店', 'category': '商品组', 'refund': '退款金额',
                    'confidence': '模型概率', 'place': '复核位', 'status': '当前处理', 'reason': '复核依据'},
        'rows': rows,
        'series': [{'label': f"{round(item['threshold']*100)}%", 'value': item['missed_cents']/100}
                   for item in replay['records'][1:]],
        'stages': [{'title': title, 'summary': summary, 'records': record['records'] + (unmatched if title == '换店去重' else []),
                    'errors': record['errors']} for title, summary, record in summaries],
    }
