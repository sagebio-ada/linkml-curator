"""LinkML generator for Synapse Curator JSON schemas.

Each template class (every class that is not abstract or a mixin) becomes a
draft-07 JSON schema shaped for Curator's grid and the RJSF forms that render it:

- properties are keyed by the PascalCase slot name (datasetAssay → DatasetAssay);
- a property's title is the slot's LinkML title, or one derived from its name;
- enum values are sorted, and if any value has a description the enum becomes
  oneOf/const entries, the only per-value metadata RJSF reads;
- integer, float, double and decimal are typed number (see CLAUDE.md);
- multivalued slots are arrays of the single-value schema.

Usage:
    gen-curator schema.yaml -d DIR       # one <Class>.json per template class
    gen-curator schema.yaml -t Class     # one class, to stdout
"""

import json
import os
import re
from dataclasses import dataclass
from importlib.metadata import version

import click
from linkml.utils.generator import Generator, shared_arguments
from linkml_runtime import SchemaView
from linkml_runtime.linkml_model.meta import SlotDefinition

__version__ = version("linkml-to-curator")

TYPES = {"integer": "number", "float": "number", "double": "number", "decimal": "number",
         "boolean": "boolean"}
FORMATS = {"date": "date", "datetime": "date-time", "uri": "uri"}


def normalise_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def pascal_case(name: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in re.split(r"[_\s]+", name))


def camel_case_to_title(name: str) -> str:
    """Convert a camelCase slot name into a Title Case label.

    A trailing "Id" word becomes "_id" (e.g. "landscapeId" -> "Landscape_id").
    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    title = spaced[:1].upper() + spaced[1:]
    if title.endswith(" Id"):
        title = title[: -len(" Id")] + "_id"
    return title


def template_classes(sv: SchemaView) -> list[str]:
    return [name for name, c in sv.all_classes().items() if not (c.abstract or c.mixin)]


def value_schema(sv: SchemaView, slot: SlotDefinition) -> dict:
    """Schema for one value of the slot."""
    enum = sv.all_enums().get(slot.range)
    if enum:
        pvs = enum.permissible_values
        if not any(pv.description for pv in pvs.values()):
            return {"enum": sorted(pvs)}
        return {"oneOf": [
            {"const": v, "title": v,
             **({"description": normalise_text(pvs[v].description)} if pvs[v].description else {})}
            for v in sorted(pvs)
        ]}

    schema = {"type": TYPES.get(slot.range, "string")}
    if slot.range in FORMATS:
        schema["format"] = FORMATS[slot.range]
    if slot.pattern:
        schema["pattern"] = slot.pattern
    if slot.minimum_value is not None:
        schema["minimum"] = slot.minimum_value
    if slot.maximum_value is not None:
        schema["maximum"] = slot.maximum_value
    return schema


def class_schema(sv: SchemaView, class_name: str) -> dict:
    properties, required = {}, []
    for name in sv.class_slots(class_name):
        slot = sv.induced_slot(name, class_name)
        value = value_schema(sv, slot)
        if slot.multivalued:
            value = {"type": "array", "items": {"type": "string", **value}}
        prop = {"title": slot.title or camel_case_to_title(name), **value}
        if slot.description:
            prop["description"] = normalise_text(slot.description)
        properties[pascal_case(name)] = prop
        if slot.required:
            required.append(pascal_case(name))

    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": f"http://example.com/{class_name}",
        "title": class_name,
        "type": "object",
        "properties": properties,
        "required": sorted(required),
    }
    if description := sv.get_class(class_name).description:
        schema["description"] = normalise_text(description)
    return schema


def _dump(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=True)


@dataclass
class CuratorGenerator(Generator):
    """Generates Synapse Curator JSON schemas, one per template class."""

    generatorname = os.path.basename(__file__)
    generatorversion = __version__
    valid_formats = ["json"]
    uses_schemaloader = False
    requires_metamodel = False

    top_class: str | None = None
    """Generate only this class."""

    directory: str | None = None
    """Write one <Class>.json per class here instead of returning the schema."""

    def serialize(self, **kwargs) -> str:
        templates = template_classes(self.schemaview)
        if self.top_class:
            if self.top_class not in templates:
                raise ValueError(f"{self.top_class!r} is not a template class: {templates}")
            templates = [self.top_class]
        if not self.directory:
            if len(templates) > 1:
                raise ValueError(
                    f"The schema has {len(templates)} template classes. "
                    "Pass --directory to write them all, or --top-class to pick one."
                )
            return _dump(class_schema(self.schemaview, templates[0]))

        os.makedirs(self.directory, exist_ok=True)
        for name in templates:
            with open(os.path.join(self.directory, f"{name}.json"), "w") as f:
                f.write(_dump(class_schema(self.schemaview, name)))
        return ""


@shared_arguments(CuratorGenerator)
@click.command(name="curator")
@click.version_option(__version__, "-V", "--version")
@click.option(
    "-d",
    "--directory",
    type=click.Path(file_okay=False),
    help="Write one <Class>.json per template class to this directory.",
)
@click.option("-t", "--top-class", help="Generate only this class, to stdout.")
def cli(yamlfile, **args):
    """Generate Synapse Curator JSON schemas from a LinkML model."""
    output = CuratorGenerator(yamlfile, **args).serialize()
    if output:
        click.echo(output)


if __name__ == "__main__":
    cli()
