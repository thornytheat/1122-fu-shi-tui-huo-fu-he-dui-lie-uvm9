from collections import defaultdict
from hashlib import sha256
from math import fsum, log

from .algorithm import calibration_blocks, calibrate, distance_guard, fit_coefficients, inputs, raw_score, usable_history
from .contracts import parse


def clipped_log_loss(p, actual):
    probability = p if actual else 1-p
    return -log(max(probability,1e-12))


def fit_block(records, train_end, cal_end, minimum_train):
    training = [row for row in records if row.labeled < train_end]
    calibration = [row for row in records if train_end <= row.labeled < cal_end and train_end <= row.arrival]
    if len(training)<minimum_train or not calibration:
        return None
    coefficients = fit_coefficients(training,iterations=90)
    blocks = calibration_blocks((raw_score(row,coefficients),row.found_mismatch) for row in calibration)
    support = distance_guard(training)
    digest = sha256(repr((training,calibration,train_end,cal_end)).encode()).hexdigest()[:16]
    return coefficients,blocks,support,digest,len(training),len(calibration)


def per_category(challenges):
    groups = defaultdict(list)
    for row in challenges:
        groups[row['category']].append(row)
    metrics = []
    for category,group in sorted(groups.items()):
        predicted = [row for row in group if row['calibrated_probability'] is not None]
        assessed = len(predicted)
        positives = sum(row['actual'] for row in predicted)
        calibration_error = abs(fsum(row['calibrated_probability'] for row in predicted)-positives)/assessed if assessed else None
        metrics.append({'category':category,'observations':len(group),'supported':assessed,'detected_mismatch':positives,
                        'calibration_gap':calibration_error,'referrals':len(group)-assessed})
    return metrics


def forward_features(row, fitted):
    coefficients, blocks, support, digest, _, _ = fitted
    raw = raw_score(row,coefficients)
    allowed = all(value<=limit for value,limit in zip(inputs(row),support,strict=True))
    score = calibrate(raw,blocks) if allowed else None
    return {'rma':row.rma,'category':row.category,'shop':row.original_shop,'day':row.arrival,'actual':row.found_mismatch,
            'calibrated_probability':score,'raw_probability':raw,'fit_id':digest,
            'log_loss':clipped_log_loss(score,row.found_mismatch) if allowed else None,
            'raw_log_loss':clipped_log_loss(raw,row.found_mismatch) if allowed else None,
            'reason':'SCORED' if allowed else 'FORWARD_PROFILE_NOVEL'}


def fold_stats(evaluation, split, fitted):
    cohort = [row for row in evaluation if row['log_loss'] is not None]
    mean = lambda field: fsum(row[field] for row in cohort)/len(cohort) if cohort else None
    return {'split':split,'ready':fitted is not None,'calibration_log_loss':mean('log_loss'),
            'raw_log_loss':mean('raw_log_loss'),'forecast_count':len(evaluation),'scored_count':len(cohort),
            'training_count':fitted[-2] if fitted else 0,'calibration_count':fitted[-1] if fitted else 0,
            'reason':'FORWARD_ASSESSED' if cohort else 'NO_SUPPORTED_FORWARD_OUTCOMES',
            'observations':evaluation,'category_reports':per_category(evaluation)}


def validate_availability(rows, *, with_labels_before, origins=(36,54,72), cal_period=10, lookahead=12, minimum_train=18):
    if not origins or tuple(sorted(set(origins)))!=tuple(origins) or min(cal_period,lookahead,minimum_train)<1:
        raise ValueError('INVALID_FORWARD_VALIDATION')
    usable = usable_history([parse(row) for row in rows],with_labels_before)
    future_seen = set()
    rolling = []
    for origin in origins:
        limit = origin+cal_period
        fitted = fit_block(usable,origin,limit,minimum_train)
        later = []
        if fitted:
            for row in usable:
                key = row.original_shop,row.rma
                if limit<=row.arrival<limit+lookahead and key not in future_seen:
                    later.append(forward_features(row,fitted))
                    future_seen.add(key)
        rolling.append(fold_stats(later,origin,fitted))
    return rolling
