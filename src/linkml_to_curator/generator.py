"""Generate JSON Schema files from namhub.model.csv.

Run after linkml_to_csv.py has regenerated the CSV from LinkML sources. The
schemas are built with synapseclient.extensions.curator.

Each property is titled after the underlying LinkML slot's camelCase name
(e.g. "datasetAssay"); restore_titles() converts that back to a
human-readable label (e.g. "Dataset Assay") before the schema is written.

Usage:
    python create_json_from_model.py
"""

import argparse
import json
import os
import re

import yaml

DATA_MODEL_SOURCE = "namhub.model.csv"
PORTAL_SCHEMA_DIR = "portal_schemas"
DATA_TYPES = [
    "Landscape",
    "Studies",
    "Datasets",
    "People",
    "Grants",
    "NAMs",
    "Publications",
]
OUTPUT_DIRECTORY = "./json_schemas"


def camel_case_to_title(name: str) -> str:
    """Convert a camelCase slot name into a human-readable Title Case label.

    A trailing "Id" word becomes "_id" (e.g. "landscapeId" -> "Landscape_id"),
    matching the source data model's identifier-naming convention.
    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    title = spaced[:1].upper() + spaced[1:]
    if title.endswith(" Id"):
        title = title[: -len(" Id")] + "_id"
    return title


def restore_titles(schema: dict) -> None:
    """Replace each property's camelCase title with a Title Case label, in place."""
    for prop in (schema.get("properties") or {}).values():
        title = prop.get("title")
        if title:
            prop["title"] = camel_case_to_title(title)


def load_enum_value_descriptions(schema_dir: str = PORTAL_SCHEMA_DIR) -> dict[str, dict[str, str]]:
    """LinkML enum name -> {permissible value: description}.
    """
    descriptions: dict[str, dict[str, str]] = {}
    for filename in ("enums.yaml", "namhub.yaml"):
        with open(os.path.join(schema_dir, filename)) as f:
            schema = yaml.safe_load(f)
        for enum_name, enum_def in (schema.get("enums") or {}).items():
            values: dict[str, str] = {}
            for value, value_def in (enum_def.get("permissible_values") or {}).items():
                desc = value_def.get("description") if isinstance(value_def, dict) else None
                if desc:
                    values[value] = re.sub(r"\s+", " ", desc).strip()
            if values:
                descriptions[enum_name] = values
    return descriptions


def load_slot_ranges(schema_dir: str = PORTAL_SCHEMA_DIR) -> dict[str, str]:
    """camelCase slot name -> LinkML range, merged with class slot_usage overrides."""
    with open(os.path.join(schema_dir, "namhub.yaml")) as f:
        namhub_schema = yaml.safe_load(f)

    ranges: dict[str, str] = {
        name: defn["range"] for name, defn in (namhub_schema.get("slots") or {}).items() if defn.get("range")
    }
    for class_def in (namhub_schema.get("classes") or {}).values():
        for slot_name, usage in (class_def.get("slot_usage") or {}).items():
            if usage.get("range"):
                ranges[slot_name] = usage["range"]
    return ranges


def _expand_enum(values: list, value_descriptions: dict) -> list:
    return [
        {
            "const": value,
            "title": value,
            **({"description": value_descriptions[value]} if value in value_descriptions else {}),
        }
        for value in values
    ]


def restore_enum_descriptions(schema: dict, slot_ranges: dict, enum_value_descriptions: dict) -> None:
    """Attach permissible-value descriptions to enum properties, in place.

    Curator emits a raw enum list, directly on the property or under "items" for
    multivalued slots, with no way to carry per-value metadata. RJSF (the form renderer
    downstream) only recognizes per-value metadata on "oneOf" entries with a "const", so
    the enum is rewritten into that shape. Must run before restore_titles(), since it keys
    off each property's original camelCase title.
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


def write_schema(schema: dict, output_path: str) -> None:
    with open(output_path, "w") as f:
        json.dump(schema, f, indent=2, sort_keys=True)


def relabel_properties(schema: dict, dmge) -> None:
    """
    This fix lets use use create_json_schema without stripping needed whitespace.
    create_json_schema(use_display_labels=True) is what keeps permissible values intact,
    but that will name everything after its LinkML camelCase slot name ("datasetAssay")
    even though the rest of the portal expects the node label from synapse ("DatasetAssay").
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


def build_with_curator(data_model_source: str, data_types: list[str], output_directory: str) -> None:
    # synapseclient.generate_jsonschema doesnt support labels we need out of the bos
    from synapseclient import Synapse
    from synapseclient.extensions.curator.schema_generation import (
        DataModelGraph,
        DataModelGraphExplorer,
        DataModelParser,
        check_curator_imports,
        create_json_schema,
    )

    check_curator_imports()
    # Only used as a logger sink — building a schema from a local CSV touches no API.
    logger = Synapse().logger

    print(f"Parsing {data_model_source}...")
    parsed = DataModelParser(path_to_data_model=data_model_source, logger=logger).parse_model()

    print("Building graph...")
    dmge = DataModelGraphExplorer(DataModelGraph(parsed).graph, logger=logger)

    print("Generating JSON schemas...")
    slot_ranges = load_slot_ranges()
    enum_value_descriptions = load_enum_value_descriptions()

    for dt in data_types:
        output_path = os.path.join(output_directory, f"{dt}.json")
        schema = create_json_schema(
            dmge=dmge,
            datatype=dt,
            schema_name=dt,
            logger=logger,
            write_schema=False,
            # Keeps permissible values as written in LinkML ("Level 1", not "Level1");
            # relabel_properties() puts the property keys back afterwards.
            use_display_labels=True,
        )
        restore_enum_descriptions(schema, slot_ranges, enum_value_descriptions)
        restore_titles(schema)
        relabel_properties(schema, dmge)
        write_schema(schema, output_path)
        n_props = len(schema.get("properties", {}))
        print(f"  {dt:<15} → {output_path}  ({n_props} properties)")




def main():
    parser = argparse.ArgumentParser(description="Generate JSON Schema files from a data model CSV.")
    parser.add_argument("--source", default=DATA_MODEL_SOURCE)
    parser.add_argument("--output", default=OUTPUT_DIRECTORY)
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    build_with_curator(args.source, DATA_TYPES, args.output)


if __name__ == "__main__":
    main()
