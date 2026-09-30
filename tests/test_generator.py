"""Shapes the NAMhub fixture doesn't exercise."""

import pytest
from linkml_runtime import SchemaView

from linkml_curator.generator import class_schema, template_classes

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
      sea_green: {title: Sea Green}
  Size:
    permissible_values:
      sm: {title: Small}
      large:
slots:
  nodesc: {}
  bounded: {range: integer, minimum_value: 1, maximum_value: 10}
  counts: {range: float, multivalued: true}
  colors: {range: Color, multivalued: true}
  snake_case_name: {pattern: "^a", multivalued: true}
  size: {range: Size}
  fancy: {title: Very Fancy}
classes:
  Base: {abstract: true, slots: [nodesc]}
  Probe:
    is_a: Base
    slots: [bounded, counts, colors, snake_case_name, size, fancy]
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
        {"const": "Sea Green", "title": "Sea Green"},
        {"const": "red", "title": "red", "description": "The red one."},
    ]}


def test_enum_value_title_is_the_value():
    assert props()["Size"] == {"title": "Size", "enum": ["Small", "large"]}


def test_linkml_title_wins():
    assert props()["Fancy"]["title"] == "Very Fancy"


@pytest.mark.parametrize("slot, message", [
    ("{range: integer, pattern: '^1'}", "pattern .* needs a string range, but its range 'integer'"),
    ("{minimum_value: 1}", "minimum_value .* needs a number range, but its range 'string'"),
    ("{range: Color, maximum_value: 3}", "maximum_value .* is emitted as an enum"),
])
def test_constraints_must_fit_the_type(slot, message):
    schema = SCHEMA.replace("fancy: {title: Very Fancy}", f"fancy: {slot}")
    with pytest.raises(ValueError, match=f"Slot 'fancy' sets {message}"):
        class_schema(SchemaView(schema), "Probe")
