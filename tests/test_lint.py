"""Each lint rule, on a schema that trips it and nothing else."""

import pytest
from click.testing import CliRunner
from linkml_runtime import SchemaView

from conftest import SCHEMA
from linkml_to_curator.lint import cli, lint

CLEAN = """
id: https://example.org/probe
name: probe
version: 1.0.0
imports: [linkml:types]
prefixes: {linkml: https://w3id.org/linkml/}
default_range: string
enums:
  Color:
    description: A colour.
    permissible_values:
      red:
      Blue:
slots:
  color: {description: Its colour., range: Color}
  count: {description: How many., range: integer}
classes:
  Probe:
    description: The one class.
    slots: [color, count]
"""


def findings(schema: str = CLEAN, **edits: str) -> set[tuple[str, str, str]]:
    for old, new in edits.items():
        assert old in schema, old
        schema = schema.replace(old, new)
    return {(f.level, f.where, f.message) for f in lint(SchemaView(schema))}


def test_clean_schema_has_no_findings():
    assert findings() == set()


def test_version_is_required():
    assert findings(**{"version: 1.0.0\n": ""}) == {
        ("error", "probe", "declares no version:, which curator-register needs")}


def test_constraint_that_does_not_fit_the_type():
    found = findings(**{"range: integer}": "range: integer, pattern: '^1'}"})
    assert len(found) == 1
    level, where, message = found.pop()
    assert (level, where) == ("error", "Probe")
    assert message.startswith("Slot 'count' sets pattern")


def test_pascal_case_collision():
    found = findings(**{"slots: [color, count]": "slots: [color, count, Count]",
                        "  count: {": "  Count: {description: Clash., range: integer}\n  count: {"})
    assert ("error", "Probe", "slots count, Count all become the property Count") in found


def test_slot_usage_must_name_a_slot_of_the_class():
    found = findings(**{"slots: [color, count]": "slots: [color, count]\n    slot_usage:\n"
                        "      other: {required: true}"})
    assert found == {("error", "Probe.slot_usage", "names other, which is not a slot of Probe")}


def test_range_must_resolve():
    assert findings(**{"range: integer}": "range: Nope}"}) == {
        ("error", "count", "range Nope is not a type, class or enum")}


@pytest.mark.parametrize("pattern, message", [
    ("'^[a'", "pattern does not compile"),
    ("'^(?P<id>\\d+)$'", "pattern uses (?P<name>)"),
])
def test_patterns(pattern, message):
    found = findings(**{"range: integer}": f"pattern: {pattern}}}"})
    assert len(found) == 1
    assert found.pop()[2].startswith(message)


def test_java_style_named_group_is_fine():
    assert findings(**{"range: integer}": "pattern: '^(?<id>\\d+)$'}"}) == set()


def test_enum_needs_values():
    found = findings(**{"    permissible_values:\n      red:\n      Blue:\n": ""})
    assert ("error", "Color", "has no permissible values") in found


def test_enum_values_are_trimmed_and_nonempty():
    found = findings(**{"      red:\n": "      ' red':\n      '  ':\n"})
    assert ("error", "Color", "value ' red' has surrounding whitespace") in found
    assert ("error", "Color", "has an empty value") in found


def test_enum_values_that_differ_only_by_case_or_punctuation():
    found = findings(**{"      Blue:\n": "      Blue:\n      RNA-seq:\n      rna seq:\n"})
    assert found == {("error", "Color",
                      "values differ only by case or punctuation: 'RNA-seq', 'rna seq'")}


def test_enum_values_are_checked_by_title():
    found = findings(**{"      Blue:\n": "      Blue:\n      rna_seq: {title: RNA-seq}\n"
                        "      rna_seq_2: {title: rna seq}\n      teal: {title: ' teal'}\n"})
    assert found == {
        ("error", "Color", "values differ only by case or punctuation: 'RNA-seq', 'rna seq'"),
        ("error", "Color", "value ' teal' has surrounding whitespace"),
    }


def test_descriptions_are_warnings():
    found = findings(**{"    description: The one class.\n": "",
                        "{description: Its colour., ": "{",
                        "    description: A colour.\n": ""})
    assert found == {("warning", "Probe", "has no description"),
                     ("warning", "color", "has no description"),
                     ("warning", "Color", "has no description")}


def test_unused_slot_and_enum_are_warnings():
    found = findings(**{"slots: [color, count]": "slots: [count]"})
    assert found == {("warning", "color", "is not a slot of any template class"),
                     ("warning", "Color", "is not the range of any slot a template class uses")}


def test_abstract_classes_do_not_count_as_use():
    found = findings(**{"    slots: [color, count]":
                        "    abstract: true\n    slots: [color, count]"})
    assert ("warning", "count", "is not a slot of any template class") in found


def test_errors_come_before_warnings():
    schema = CLEAN.replace("version: 1.0.0\n", "")
    schema = schema.replace("slots: [color, count]", "slots: [count]")
    levels = [f.level for f in lint(SchemaView(schema))]
    assert levels == sorted(levels, key=lambda lvl: lvl != "error")


def test_cli_on_the_fixture_model():
    result = CliRunner().invoke(cli, [str(SCHEMA)])
    assert result.exit_code == 0, result.output
    assert "warning  datasetId_list: is not a slot of any template class" in result.output
    assert "warning  NamContextEnum: is not the range of any slot" in result.output
    assert result.output.rstrip().endswith("0 error(s), 2 warning(s)")
    assert CliRunner().invoke(cli, [str(SCHEMA), "--strict"]).exit_code == 1


def test_cli_strict_fails_on_warnings(tmp_path):
    schema = tmp_path / "s.yaml"
    schema.write_text(CLEAN.replace("slots: [color, count]", "slots: [count]"))
    assert CliRunner().invoke(cli, [str(schema)]).exit_code == 0
    assert CliRunner().invoke(cli, [str(schema), "--strict"]).exit_code == 1
