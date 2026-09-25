"""Shapes the NAMhub fixture doesn't exercise."""

from linkml_runtime import SchemaView

from linkml_to_curator.generator import class_schema, template_classes

SCHEMA = """
id: https://example.org/probe
name: probe
imports: [linkml:types]
prefixes: {linkml: https://w3id.org/linkml/}
default_range: string
enums:
  Color:
    permissible_values:
      red: {description: The red one.}
      Blue:
slots:
  nodesc: {}
  bounded: {range: integer, minimum_value: 1, maximum_value: 10}
  counts: {range: float, multivalued: true}
  colors: {range: Color, multivalued: true}
  snake_case_name: {pattern: "^a", multivalued: true}
  fancy: {title: Very Fancy}
classes:
  Base: {abstract: true, slots: [nodesc]}
  Probe:
    is_a: Base
    slots: [bounded, counts, colors, snake_case_name, fancy]
"""


def props() -> dict:
    return class_schema(SchemaView(SCHEMA), "Probe")["properties"]


def test_abstract_classes_are_not_templates():
    assert template_classes(SchemaView(SCHEMA)) == ["Probe"]


def test_inherited_slot_without_description():
    assert props()["Nodesc"] == {"title": "Nodesc", "type": "string"}


def test_bounds_as_written():
    assert props()["Bounded"] == {"title": "Bounded", "type": "number", "minimum": 1, "maximum": 10}


def test_multivalued_values_are_arrays():
    p = props()
    assert p["Counts"]["items"] == {"type": "number"}
    assert p["SnakeCaseName"] == {
        "title": "Snake_case_name", "type": "array", "items": {"type": "string", "pattern": "^a"}
    }
    assert p["Colors"]["items"] == {"type": "string", "oneOf": [
        {"const": "Blue", "title": "Blue"},
        {"const": "red", "title": "red", "description": "The red one."},
    ]}


def test_linkml_title_wins():
    assert props()["Fancy"]["title"] == "Very Fancy"
