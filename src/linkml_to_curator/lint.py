"""Check a LinkML model against what Curator and Synapse will accept.

Errors are things `gen-curator` or `curator-register` cannot work with, or that Synapse
would reject: no `version:`, constraints that don't fit a slot's type, slots whose
PascalCase keys collide, patterns Synapse's Java regex engine can't run, empty or
duplicated enum values, and names that don't resolve. Warnings are things the model
would be better without but Curator tolerates: missing descriptions, and slots or enums
nothing uses.

Usage:
    curator-lint schema.yaml            # exit 1 on errors
    curator-lint schema.yaml --strict   # exit 1 on warnings too
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

import click
from linkml_runtime import SchemaView

from linkml_to_curator import __version__
from linkml_to_curator.generator import class_schema, enum_values, pascal_case, template_classes

Level = Literal["error", "warning"]

PYTHON_ONLY_REGEX = re.compile(r"\(\?P[<=]")
"""Named groups in Python syntax; Java, which validates on Synapse, spells them (?<name>)."""

JAVA_NAMED_GROUP = re.compile(r"\(\?<(?=[A-Za-z])")
"""A Java named group opener, as opposed to a lookbehind (?<= or (?<!."""


def compile_as_java(pattern: str) -> None:
    """Compile the pattern the way Synapse's Java engine reads it; raise re.error if it can't."""
    re.compile(JAVA_NAMED_GROUP.sub("(?P<", pattern))


@dataclass(frozen=True)
class Finding:
    level: Level
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level:<8} {self.where}: {self.message}"


def normalise_value(value: str) -> str:
    """Key under which two enum values count as the same: case and punctuation ignored."""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def lint(sv: SchemaView) -> list[Finding]:
    """Every finding for the schema, errors first, in schema order within each level."""
    errors: list[Finding] = []
    warnings: list[Finding] = []
    templates = template_classes(sv)
    classes, slots, enums = sv.all_classes(), sv.all_slots(), sv.all_enums()
    known_ranges = set(sv.all_types()) | set(classes) | set(enums)

    if not sv.schema.version:
        errors.append(Finding("error", sv.schema.name,
                              "declares no version:, which curator-register needs"))

    for name in templates:
        try:
            class_schema(sv, name)
        except ValueError as e:
            errors.append(Finding("error", name, str(e)))
        keys = defaultdict(list)
        for slot in sv.class_slots(name):
            keys[pascal_case(slot)].append(slot)
        for key, names in keys.items():
            if len(names) > 1:
                errors.append(Finding(
                    "error", name, f"slots {', '.join(names)} all become the property {key}"))

    for name, cls in classes.items():
        for used in cls.slot_usage:
            if used not in sv.class_slots(name):
                errors.append(Finding("error", f"{name}.slot_usage",
                                      f"names {used}, which is not a slot of {name}"))
        if not cls.description:
            warnings.append(Finding("warning", name, "has no description"))

    used_slots = {s for name in templates for s in sv.class_slots(name)}
    used_enums = {sv.induced_slot(s, name).range
                  for name in templates for s in sv.class_slots(name)}
    for name, slot in slots.items():
        if slot.range and slot.range not in known_ranges:
            errors.append(Finding(
                "error", name, f"range {slot.range} is not a type, class or enum"))
        if slot.pattern:
            try:
                compile_as_java(slot.pattern)
            except re.error as e:
                errors.append(Finding("error", name, f"pattern does not compile: {e}"))
            if PYTHON_ONLY_REGEX.search(slot.pattern):
                errors.append(Finding(
                    "error", name, "pattern uses (?P<name>), which Synapse's regex engine "
                    "does not support; write (?<name>)"))
        if not slot.description:
            warnings.append(Finding("warning", name, "has no description"))
        if name not in used_slots:
            warnings.append(Finding("warning", name, "is not a slot of any template class"))

    for name, enum in enums.items():
        values = [v for v, _ in enum_values(enum)]
        if not values:
            errors.append(Finding("error", name, "has no permissible values"))
        seen = defaultdict(list)
        for value in values:
            if not value.strip():
                errors.append(Finding("error", name, "has an empty value"))
            elif value != value.strip():
                errors.append(Finding("error", name, f"value {value!r} has surrounding whitespace"))
            seen[normalise_value(value)].append(value)
        for same in seen.values():
            if len(same) > 1:
                errors.append(Finding(
                    "error", name, "values differ only by case or punctuation: "
                    + ", ".join(repr(v) for v in same)))
        if not enum.description:
            warnings.append(Finding("warning", name, "has no description"))
        if name not in used_enums:
            warnings.append(Finding(
                "warning", name, "is not the range of any slot a template class uses"))

    return errors + warnings


@click.command()
@click.version_option(__version__, "-V", "--version")
@click.argument("schema", type=click.Path(exists=True, dir_okay=False))
@click.option("--strict", is_flag=True, help="Exit with an error status on warnings too.")
def cli(schema: str, strict: bool):
    """Check a LinkML SCHEMA against what Curator and Synapse will accept."""
    findings = lint(SchemaView(schema))
    for finding in findings:
        click.echo(str(finding))
    errors = sum(f.level == "error" for f in findings)
    warnings = len(findings) - errors
    click.echo(f"{errors} error(s), {warnings} warning(s)")
    if errors or (strict and warnings):
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
