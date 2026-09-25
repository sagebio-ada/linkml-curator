import pytest
from linkml_runtime import SchemaView

from linkml_to_curator.datamodel_csv import data_model_rows

SCHEMA = """
id: https://example.org/test
name: test
imports: [linkml:types]
prefixes: {linkml: https://w3id.org/linkml/}
default_range: string
slots:
  count: {range: integer}
classes:
  Base: {abstract: true, slots: [count]}
  A: {is_a: Base}
  B: {is_a: Base, slot_usage: {count: {range: string}}}
"""


def test_abstract_classes_are_not_templates():
    sv = SchemaView(SCHEMA.replace("slot_usage: {count: {range: string}}", "slots: []"))
    templates = [r["Attribute"] for r in data_model_rows(sv) if r.get("IsTemplate")]
    assert templates == ["A", "B"]


def test_conflicting_slot_usage_is_an_error():
    with pytest.raises(ValueError, match="'count' has range='string' in B"):
        data_model_rows(SchemaView(SCHEMA))
