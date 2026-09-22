from sqlalchemy.sql.elements import BinaryExpression
from sqlalchemy.sql.elements import BooleanClauseList

from api.filtering.db_filters import _tags_filter


def test_tags_filter_empty_list():
    filters = _tags_filter([])
    assert filters == []


def test_tags_filter_single_tag():
    filters = _tags_filter(["ns1/key1=val1"])
    assert len(filters) == 1
    # or_() with single element or BooleanClauseList
    condition = filters[0]
    assert isinstance(condition, (BinaryExpression, BooleanClauseList))


def test_tags_filter_same_identity_grouped_with_or():
    """
    Multiple tags with the same namespace and key should produce a single
    filter condition containing an OR expression of all values.
    """
    filters = _tags_filter(["ns1/key1=val1", "ns1/key1=val2", "ns1/key1=val3"])
    assert len(filters) == 1
    condition = filters[0]
    # In SQLAlchemy, or_() with multiple clauses is a BooleanClauseList
    assert isinstance(condition, BooleanClauseList)
    assert len(condition.clauses) == 3


def test_tags_filter_different_identities_separate_conditions():
    """
    Tags with different identities (different namespace or different key)
    should produce separate filter conditions (which are AND'd by the caller).
    """
    filters = _tags_filter(["ns1/key1=val1", "ns2/key1=val1", "ns1/key2=val1"])
    assert len(filters) == 3


def test_tags_filter_null_namespace_same_key_grouped_with_or():
    """
    Tags with no namespace (None) and the same key should be grouped into
    a single OR condition.
    """
    filters = _tags_filter(["key1=val1", "key1=val2"])
    assert len(filters) == 1
    condition = filters[0]
    assert isinstance(condition, BooleanClauseList)
    assert len(condition.clauses) == 2


def test_tags_filter_null_namespace_vs_named_namespace_distinct_identities():
    """
    A tag with null namespace and a tag with a named namespace should be
    treated as distinct identities even if they share the same key name.
    """
    filters = _tags_filter(["key1=val1", "ns1/key1=val1"])
    assert len(filters) == 2


def test_tags_filter_mixed_same_and_different_identities():
    """
    A mix of tags where some share identities and some are distinct should
    produce one condition per unique (namespace, key) identity.
    """
    string_tags = [
        "ns1/env=prod",
        "ns1/env=stage",
        "ns2/app=web",
        "ns2/app=api",
        "region=us-east",
    ]
    filters = _tags_filter(string_tags)
    # Unique identities: (ns1, env), (ns2, app), (None, region) -> 3 conditions
    assert len(filters) == 3

    # Check that (ns1, env) and (ns2, app) have 2 clauses each, and (None, region) has 1
    clause_lengths = sorted(len(cond.clauses) if isinstance(cond, BooleanClauseList) else 1 for cond in filters)
    assert clause_lengths == [1, 2, 2]
