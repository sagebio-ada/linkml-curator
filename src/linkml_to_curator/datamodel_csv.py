"""Build the Synapse Curator data-model CSV from a LinkML schema.

Curator builds JSON schemas from a CSV with one template row per class and one
attribute row per slot. Headers:
    Attribute, Description, Valid Values, DependsOn, Required, Properties,
    Validation Rules, columnType, Format, Pattern, Minimum, Maximum,
    IsTemplate, Source

Mapping from LinkML:
    class              → template row: DependsOn = class slots, IsTemplate = True
    slot               → attribute row, emitted once however many classes use it
    required           → Required = True if the slot is required in any class
    range: <Enum>      → Valid Values = comma-separated permissible values
    range: date        → columnType = string, Format = date
    range: uri         → columnType = string, Format = uri
    range: integer     → columnType = number
    range: boolean     → columnType = boolean
    multivalued: true  → columnType gets a "_list" suffix (string/boolean)
    pattern            → Pattern
    minimum_value/maximum_value → Minimum/Maximum

Usage:
    python -m linkml_to_curator.datamodel_csv [--schema namhub.yaml] [--output namhub.model.csv]
"""

import argparse
import csv
import io
import re

from linkml_runtime import SchemaView
from linkml_runtime.linkml_model.meta import SlotDefinition

CURATOR_HEADERS = [
    "Attribute",
    "Description",
    "Valid Values",
    "DependsOn",
    "Required",
    "Properties",
    "Validation Rules",
    "columnType",
    "Format",
    "Pattern",
    "Minimum",
    "Maximum",
    "IsTemplate",
    "Source",
]

# Fields an attribute row carries. The row is shared by every class using the slot,
# so the classes must agree on them.
SHARED_FIELDS = ("range", "multivalued", "pattern", "minimum_value", "maximum_value")


def normalise_text(s: str | None) -> str:
    return re.sub(r"\s+", " ", s).strip() if s else ""


def template_classes(sv: SchemaView) -> list[str]:
    """Classes that become Curator templates: every class that is not abstract or a mixin."""
    return [name for name, c in sv.all_classes().items() if not (c.abstract or c.mixin)]


def get_column_type(slot: SlotDefinition) -> tuple[str, str]:
    """Return (columnType, Format) for a slot based on its LinkML range.

    integer maps to number: Synapse types a DOUBLE column from its data, and its
    validator rejects a double such as 30.0 against a JSON "integer".
    """
    if slot.range == "date":
        base, fmt = "string", "date"
    elif slot.range == "uri":
        base, fmt = "string", "uri"
    elif slot.range == "integer":
        base, fmt = "number", ""
    elif slot.range == "boolean":
        base, fmt = "boolean", ""
    else:
        # plain string range, or an enum range (valid values carry the constraint)
        base, fmt = "string", ""

    if slot.multivalued and base in ("string", "boolean"):
        return f"{base}_list", fmt
    return base, fmt


def attribute_row(sv: SchemaView, slot_name: str, class_names: list[str]) -> dict:
    induced = [sv.induced_slot(slot_name, c) for c in class_names]
    slot = induced[0]
    for other, class_name in zip(induced[1:], class_names[1:], strict=True):
        for field in SHARED_FIELDS:
            if getattr(other, field) != getattr(slot, field):
                raise ValueError(
                    f"Slot {slot_name!r} has {field}={getattr(other, field)!r} in "
                    f"{class_name} but {getattr(slot, field)!r} in {class_names[0]}. "
                    "The Curator CSV has one row per slot and cannot represent both."
                )

    enum = sv.all_enums().get(slot.range)
    column_type, fmt = get_column_type(slot)
    return {
        "Attribute": slot_name,
        "Description": normalise_text(slot.description),
        "Valid Values": ", ".join(enum.permissible_values) if enum else "",
        "Required": str(any(s.required for s in induced)),
        "columnType": column_type,
        "Format": fmt,
        "Pattern": slot.pattern or "",
        "Minimum": "" if slot.minimum_value is None else slot.minimum_value,
        "Maximum": "" if slot.maximum_value is None else slot.maximum_value,
    }


def data_model_rows(sv: SchemaView) -> list[dict]:
    templates = template_classes(sv)
    slot_classes = {c: sv.class_slots(c) for c in templates}

    rows: list[dict] = []
    emitted: set[str] = set()
    for class_name, slots in slot_classes.items():
        rows.append({
            "Attribute": class_name,
            "Description": normalise_text(sv.get_class(class_name).description),
            "DependsOn": ", ".join(slots),
            "IsTemplate": "True",
        })
        for slot_name in slots:
            if slot_name in emitted:
                continue
            emitted.add(slot_name)
            users = [c for c, s in slot_classes.items() if slot_name in s]
            rows.append(attribute_row(sv, slot_name, users))
    return rows


def data_model_csv(sv: SchemaView) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CURATOR_HEADERS, restval="")
    writer.writeheader()
    writer.writerows(data_model_rows(sv))
    return out.getvalue()


def main():
    parser = argparse.ArgumentParser(description="Convert a LinkML schema to a Curator CSV.")
    parser.add_argument("--output", default="namhub.model.csv")
    parser.add_argument("--schema", default="portal_schemas/namhub.yaml")
    args = parser.parse_args()

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        f.write(data_model_csv(SchemaView(args.schema)))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
