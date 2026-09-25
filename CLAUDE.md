# CLAUDE.md

This file records the reasons behind choices that look arbitrary in the code. Read it before
changing generator behavior.

## The pipeline

`gen-curator` converts the LinkML schema to Curator's data-model CSV (`datamodel_csv.py`).
synapseclient's curator extension builds a graph from that CSV and emits one JSON schema per
template class. `generator.py` then post-processes each schema. `tests/fixtures/expected/`
is the output for the NAMhub model, and every change to it should be deliberate.

## Why the generator calls non-public curator functions

`generate_jsonschema`, the public entry point, sets
`use_display_labels=(data_model_labels == "display_label")`, and that one flag controls both
enum values and property keys. With class labels, permissible values come out as node labels
("Level1" rather than "Level 1"). No combination of its arguments yields spaced enum values
together with PascalCase property keys. The generator therefore calls `create_json_schema`
with `use_display_labels=True` and `relabel_properties()` restores the keys. The last
synapseclient version checked was 4.13.0. If synapseclient decouples the two, switch back to
`generate_jsonschema`.

## integer maps to number

Synapse infers a RecordSet column's type from its data: a single `2.5` or `30.0` makes the
column DOUBLE. Its validator, everit json-schema, accepts only Integer/Long/BigInteger for
`"type": "integer"`, so a double such as `30.0` would fail. Typing integer slots as `number`
lets fractional counts through. Keep `range: integer` in the model for its meaning.

## One CSV row per slot

Curator's data model has one attribute row per slot, shared by every template that uses it.
Consequences:

- When classes disagree on a slot's range, multivalued, pattern or bounds, generation stops
  with an error. The CSV can't represent both.
- Required is the union across classes in the CSV. The generator then filters each
  schema's `required` down to the slots that class requires.

## Registration versions

`curator-register` takes its version from the model's `version:`. A version that already
exists for any class stops the whole run before anything is stored, so a release is a
deliberate bump of `version:` and every class shares one version.
