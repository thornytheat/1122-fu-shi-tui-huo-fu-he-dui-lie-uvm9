from dataclasses import replace
import math

import pytest

from returnscope.shop_identity.contracts import ReturnIdentity, InvalidRow, parse
from returnscope.shop_identity.service import evaluate, validate
from returnscope.shop_identity import algorithm

def identity(**changes):
    return dict(rma='R9', shop='S1', parcel_key='PX:A112233', customer='CUS-A', original_shop='S1',
                arrival=39, submitted=37, weight=320, seal=True) | changes


def test_store_aliases_do_not_change_primary_authorization_when_permuted():  # TRAP-22
    forwarded = identity(shop='S3', submitted=35, parcel_key='PX:B456789')
    values = [identity(), forwarded]
    assert evaluate(values) == evaluate(reversed(values))
    assert evaluate(values)['records'][0]['shop'] == 'S1'


def test_different_customer_same_parcel_is_put_on_hold():
    row = evaluate([identity(), identity(customer='CUS-B')])['records'][0]
    assert row['reason'] == 'PARCEL_OWNER_CONFLICT'
    assert row['valid'] is False


def test_distinct_rma_under_same_shipment_does_not_duplicate_refund():
    row = evaluate([identity(), identity(rma='R8')])['records'][0]
    assert row['reason'] == 'MULTIPLE_REFUND_AUTHORIZATIONS'


def test_label_alias_can_create_transitive_components():
    events = [identity(), identity(shop='S3', parcel_key='PX:B456789'),
              identity(shop='S4', parcel_key='PX:B456789', customer='CUS-C')]
    rows = evaluate(events)['records']
    assert len(rows) == 1
    assert rows[0]['alias_shops'] == ['S1', 'S3', 'S4']
    assert rows[0]['duplicate_count'] == 2


def test_same_rma_in_separate_original_shops_remains_independent():
    rows = evaluate([identity(), identity(original_shop='S2', parcel_key='SX:K44444')])['records']
    assert len(rows) == 2
    assert all(row['valid'] for row in rows)


def test_nonempty_customer_is_required():
    assert evaluate([identity(customer='')])['rejected_count'] == 1


def test_same_customer_and_unique_labels_without_matching_rma_are_separate():
    rows = evaluate([identity(), identity(rma='R3', parcel_key='PX:AD34455')])['records']
    assert [row['rma'] for row in rows] == ['R3', 'R9']


def test_component_linking_is_idempotent():
    groups = algorithm.ReturnEquivalence(3)
    groups.merge(0, 1)
    groups.merge(1, 0)
    groups.merge(1, 2)
    assert len({groups.find(i) for i in range(3)}) == 1
    assert groups.weights[groups.find(1)] == 3
