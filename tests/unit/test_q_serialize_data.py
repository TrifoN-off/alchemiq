from datetime import UTC, datetime
from decimal import Decimal

import pytest

from alchemiq import Model
from alchemiq.exceptions import DeserializationError, DisallowedFieldError
from alchemiq.query import Q
from alchemiq.types import PK, Money
from alchemiq.types.temporal import DateTimeTz


class Account(Model):
    __tablename__ = "serialize_account"

    id: PK[int]
    name: str
    balance: Money
    created_at: DateTimeTz


def test_leaf_to_data_is_compact():
    assert Q(name="neo").to_data() == [0, 0, [["name", "neo"]]]


def test_lookup_key_kept_whole():
    assert Q(name__icontains="neo").to_data() == [0, 0, [["name__icontains", "neo"]]]


def test_or_node_encodes_connector_code():
    assert (Q(name="a") | Q(name="b")).to_data()[0] == 1  # 1 == OR


def test_roundtrip_simple():
    q = Q(name__icontains="neo") & Q(name="trinity")
    assert Q.from_data(q.to_data(), model=Account) == q


def test_roundtrip_typed_values():
    q = Q(balance__gte=Decimal("10.00")) | Q(created_at__lt=datetime(2026, 1, 1, tzinfo=UTC))
    assert Q.from_data(q.to_data(), model=Account) == q


def test_in_and_range_value_kinds():
    q = Q(balance__in=[Decimal("1.00"), Decimal("2.00")]) & Q(id__range=(1, 9))
    assert Q.from_data(q.to_data(), model=Account) == q


def test_default_whitelist_allows_model_fields():
    q = Q(name="neo")
    assert Q.from_data(q.to_data(), model=Account) == q


def test_unknown_field_rejected():
    with pytest.raises(DisallowedFieldError):
        Q.from_data([0, 0, [["secret", 1]]], model=Account)


def test_deny_blocks_field():
    with pytest.raises(DisallowedFieldError):
        Q.from_data(Q(name="neo").to_data(), model=Account, deny={"name"})


def test_allow_restricts_to_subset():
    with pytest.raises(DisallowedFieldError):
        Q.from_data(Q(balance__gte=Decimal("1.00")).to_data(), model=Account, allow={"name"})


def test_malformed_payload_raises():
    with pytest.raises(DeserializationError):
        Q.from_data({"not": "a-list"}, model=Account)


def test_malformed_list_value_raises():
    with pytest.raises(DeserializationError):
        Q.from_data([0, 0, [["id__in", 42]]], model=Account)


def test_malformed_range_arity_raises():
    with pytest.raises(DeserializationError):
        Q.from_data([0, 0, [["id__range", [1, 2, 3]]]], model=Account)


def test_negated_roundtrip():
    q = ~Q(name="neo")
    assert Q.from_data(q.to_data(), model=Account) == q
