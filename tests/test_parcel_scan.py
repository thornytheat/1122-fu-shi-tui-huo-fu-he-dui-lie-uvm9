from dataclasses import replace
import math

import pytest

from returnscope.parcel_scan.contracts import ParcelScan, InvalidRow, parse
from returnscope.parcel_scan.service import evaluate, validate
from returnscope.parcel_scan import algorithm

def scan(**changes):
    return dict(rma='R19', shop='SX01', carrier='PX', label='AB 227-C', arrival=39, observed=40,
                weight=420, seal=True, revision=1) | changes


def test_labels_are_canonicalized_with_carrier_namespace():
    assert algorithm.label_fingerprint('px', 'ab 227-c') == 'PX:AB227C'
    assert algorithm.label_fingerprint('zx', 'AB227c') != 'PX:AB227C'


def test_exact_close_is_next_statement():  # TRAP-23
    result = evaluate([scan(observed=41)], statement_close=41)['records'][0]
    assert result['valid'] is False
    assert result['reason'] == 'ARRIVED_AFTER_CLOSE'


def test_latest_revision_can_repair_a_weight():
    result = evaluate([scan(), scan(revision=2, observed=49, weight=350)], statement_close=50)['records'][0]
    assert (result['weight'], result['superseded_scans']) == (350, 1)


def test_old_revision_is_inert_after_new_scan():  # TRAP-26
    first = scan(revision=4)
    delayed = scan(revision=3, observed=42, weight=300)
    evidence = evaluate([first, delayed], statement_close=50)['records'][0]
    assert evidence['revision'] == 4 and evidence['weight'] == 420


def test_conflicting_revision_is_quarantined():
    result = evaluate([scan(), scan(weight=675, observed=41)], statement_close=50)['records'][0]
    assert result['reason'] == 'SCAN_REVISION_CONFLICT'
    assert result['parcel_key'] is None


def test_barcode_requires_real_identifier():
    assert evaluate([scan(label='包装太轻')], statement_close=50)['records'][0]['reason'] == 'LABEL_UNREADABLE'


def test_bad_station_clock_has_a_distinct_reason():
    assert evaluate([scan(observed=38)], statement_close=50)['records'][0]['reason'] == 'STATION_CLOCK_INVALID'


def test_missing_rma_isolated_with_line_number():
    result = evaluate([scan(), scan(rma=' ')], statement_close=50)
    assert len(result['records']) == 1
    assert result['errors'] == [{'line': 2, 'field': 'parcel_scan.rma', 'code': 'EXPECTED_NONEMPTY_TEXT'}]
