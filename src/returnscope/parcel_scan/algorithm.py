from __future__ import annotations

from .contracts import ParcelScan

from collections import defaultdict
from dataclasses import asdict


def label_fingerprint(carrier, label):
    readable = ''.join(ch for ch in label.strip().upper() if ch not in ' -')
    if not readable.isascii() or not readable.isalnum() or not 6 <= len(readable) <= 48:
        raise ValueError('LABEL_UNREADABLE')
    return carrier.upper() + ':' + readable


def reject_reason(scan, statement_close):
    if scan.observed < scan.arrival:
        return 'STATION_CLOCK_INVALID'
    if scan.arrival >= statement_close or scan.observed >= statement_close:
        return 'ARRIVED_AFTER_CLOSE'
    return None


def revision_signature(scan):
    return scan.shop, scan.arrival, scan.weight, scan.seal, label_fingerprint(scan.carrier, scan.label)


def classify_revisions(group):
    ranks = sorted(group, key=lambda item: (-item.revision, item.observed, item.rma, item.label, item.shop))
    rank = ranks[0].revision
    same_version = [item for item in ranks if item.revision == rank]
    if len({revision_signature(row) for row in same_version}) != 1:
        return ranks[0], 'SCAN_REVISION_CONFLICT', len(ranks) - 1
    return ranks[0], 'READY_TO_INSPECT', len(ranks) - 1


def audit_row(scan, valid, reason, extra=0):
    return asdict(scan) | {
        'parcel_key': label_fingerprint(scan.carrier, scan.label) if valid else None,
        'valid': valid,
        'reason': reason,
        'superseded_scans': extra,
    }


def calculate(records, *, statement_close):
    shipments = defaultdict(list)
    evidence = []
    for scan in records:
        reason = reject_reason(scan, statement_close)
        if reason is None:
            try:
                label_fingerprint(scan.carrier, scan.label)
            except ValueError as error:
                reason = str(error)
        if reason:
            evidence.append(audit_row(scan, False, reason))
        else:
            shipments[scan.shop, scan.rma].append(scan)
    for rows in shipments.values():
        selected, reason, dropped = classify_revisions(rows)
        evidence.append(audit_row(selected, reason == 'READY_TO_INSPECT', reason, dropped))
    return sorted(evidence, key=lambda item: (item['arrival'], item['shop'], item['rma'], item['reason']))
