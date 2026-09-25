"""LinkML generator for Synapse Curator JSON schemas.

The schema is converted to Curator's data-model CSV (see datamodel_csv), which
synapseclient.extensions.curator turns into one JSON schema per template class.
Those schemas are then post-processed:

- enum values with descriptions become oneOf/const entries, which RJSF renders;
- property titles come from the slot's LinkML title, or from its name;
- property keys go back to Curator's PascalCase node labels.

Usage:
    gen-curator schema.yaml -d DIR       # one <Class>.json per template class
    gen-curator schema.yaml -t Class     # one class, to stdout
    gen-curator schema.yaml -f csv       # the intermediate data-model CSV
"""

import json
import os
import re
import tempfile
from dataclasses import dataclass
from importlib.metadata import version

import click
from linkml.utils.generator import Generator, shared_arguments

from linkml_to_curator.datamodel_csv import data_model_csv, normalise_text, template_classes

__version__ = version("linkml-to-curator")


def camel_case_to_title(name: str) -> str:
    """Convert a camelCase slot name into a human-readable Title Case label.

    A trailing "Id" word becomes "_id" (e.g. "landscapeId" -> "Landscape_id").
    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    title = spaced[:1].upper() + spaced[1:]
    if title.endswith(" Id"):
        title = title[: -len(" Id")] + "_id"
    return title


def restore_titles(schema: dict, titles: dict[str, str | None]) -> None:
    """Replace each property's slot-name title with its LinkML title, in place.

    titles maps slot name to the slot's LinkML title; a slot without one gets
    camel_case_to_title() of its name.
    """
    for prop in (schema.get("properties") or {}).values():
        name = prop.get("title")
        if name:
            prop["title"] = titles.get(name) or camel_case_to_title(name)


def _expand_enum(values: list, value_descriptions: dict) -> list:
    return [
        {
            "const": value,
            "title": value,
            **({"description": value_descriptions[value]} if value in value_descriptions else {}),
        }
        for value in values
    ]


def restore_enum_descriptions(
    schema: dict, slot_ranges: dict, enum_value_descriptions: dict
) -> None:
    """Attach permissible-value descriptions to enum properties, in place.

    Curator emits a raw enum list, directly on the property or under "items" for
    multivalued slots, with no way to carry per-value metadata. RJSF (the form renderer
    downstream) only recognizes per-value metadata on "oneOf" entries with a "const", so
    the enum is rewritten into that shape. Must run before restore_titles(), since it keys
    off each property's slot-name title.
    """
    for prop in (schema.get("properties") or {}).values():
        slot_name = prop.get("title")
        if not slot_name:
            continue
        value_descriptions = enum_value_descriptions.get(slot_ranges.get(slot_name))
        if not value_descriptions:
            continue

        if "items" in prop and "enum" in prop["items"]:
            prop["items"]["oneOf"] = _expand_enum(prop["items"]["enum"], value_descriptions)
            del prop["items"]["enum"]
        elif "enum" in prop:
            prop["oneOf"] = _expand_enum(prop["enum"], value_descriptions)
            del prop["enum"]


def relabel_properties(schema: dict, dmge) -> None:
    """Rename property keys from slot names ("datasetAssay") to node labels ("DatasetAssay").

    create_json_schema(use_display_labels=True) is what keeps permissible values intact,
    but that same flag keys every property by its slot name, while the portal expects
    Curator's node label.
    """

    def label(display_name: str) -> str:
        node_label = dmge.get_node_label(display_name)
        if not node_label:
            raise ValueError(f"No node in the data model graph for property {display_name!r}.")
        return node_label

    labels = {name: label(name) for name in (schema.get("properties") or {})}
    schema["properties"] = {labels[name]: prop for name, prop in schema["properties"].items()}
    if schema.get("required"):
        schema["required"] = [labels.get(name) or label(name) for name in schema["required"]]


@dataclass
class CuratorGenerator(Generator):
    """Generates Synapse Curator JSON schemas, one per template class."""

    generatorname = os.path.basename(__file__)
    generatorversion = __version__
    valid_formats = ["json", "csv"]
    uses_schemaloader = False
    requires_metamodel = False

    top_class: str | None = None
    """Generate only this class."""

    directory: str | None = None
    """Write one <Class>.json per class here instead of returning the schema."""

    def serialize(self, **kwargs) -> str:
        if self.format == "csv":
            return data_model_csv(self.schemaview)

        templates = template_classes(self.schemaview)
        if self.top_class:
            if self.top_class not in templates:
                raise ValueError(f"{self.top_class!r} is not a template class: {templates}")
            templates = [self.top_class]
        if not self.directory and len(templates) > 1:
            raise ValueError(
                f"The schema has {len(templates)} template classes. "
                "Pass --directory to write them all, or --top-class to pick one."
            )

        schemas = self.build(templates)
        if not self.directory:
            return _dump(schemas[templates[0]])
        os.makedirs(self.directory, exist_ok=True)
        for name, schema in schemas.items():
            with open(os.path.join(self.directory, f"{name}.json"), "w") as f:
                f.write(_dump(schema))
        return ""

    def build(self, class_names: list[str]) -> dict[str, dict]:
        """Build each class's post-processed JSON schema through Curator."""
        # Why the non-public create_json_schema: the public generate_jsonschema ties
        # use_display_labels to property-key format, and no combination of its arguments
        # yields space-preserving enum values with node-label keys.
        from synapseclient.extensions.curator.schema_generation import (
            DataModelGraph,
            DataModelGraphExplorer,
            DataModelParser,
            check_curator_imports,
            create_json_schema,
        )

        check_curator_imports()
        sv = self.schemaview
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "model.csv")
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                f.write(data_model_csv(sv))
            parsed = DataModelParser(path_to_data_model=csv_path, logger=self.logger).parse_model()
        dmge = DataModelGraphExplorer(DataModelGraph(parsed).graph, logger=self.logger)

        enum_value_descriptions = {
            enum_name: values
            for enum_name, enum in sv.all_enums().items()
            if (values := {
                text: normalise_text(pv.description)
                for text, pv in enum.permissible_values.items()
                if pv.description
            })
        }

        schemas = {}
        for class_name in class_names:
            slots = {s: sv.induced_slot(s, class_name) for s in sv.class_slots(class_name)}
            schema = create_json_schema(
                dmge=dmge,
                datatype=class_name,
                schema_name=class_name,
                logger=self.logger,
                write_schema=False,
                # Keeps permissible values as written in LinkML ("Level 1", not "Level1");
                # relabel_properties() puts the property keys back afterwards.
                use_display_labels=True,
            )
            restore_enum_descriptions(
                schema, {s: slot.range for s, slot in slots.items()}, enum_value_descriptions
            )
            # The CSV's Required column is shared by every class using a slot; keep only
            # the slots this class requires.
            schema["required"] = [s for s in schema.get("required", []) if slots[s].required]
            restore_titles(schema, {s: slot.title for s, slot in slots.items()})
            relabel_properties(schema, dmge)
            schemas[class_name] = schema
        return schemas


def _dump(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=True)


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
        click.echo(output, nl=not output.endswith("\n"))


if __name__ == "__main__":
    cli()
