# CLAUDE.md

This file records the reasons behind choices that look arbitrary in the code. Read it before
changing generator behavior.

## The generator writes Curator's JSON shape itself

`gen-curator` builds each schema straight from SchemaView. It does not go through
synapseclient's curator extension, which needs a CSV data model and a graph. That route keyed
every enum value and property off one `use_display_labels` flag, so it could not produce
space-preserving enum values together with PascalCase keys, and the generator ended up
undoing most of its output. The JSON matches what that route produced for the NAMhub model
byte for byte (`tests/fixtures/expected/`). Where the NAMhub model didn't exercise it, the
route had quirks that are deliberately not reproduced: "TBD" for missing descriptions,
multivalued numbers emitted as scalars, and `float` typed as `string`.

`$id` is a placeholder; `curator-register` sets the real one.

## integer maps to number

Synapse infers a RecordSet column's type from its data: a single `2.5` or `30.0` makes the
column DOUBLE. Its validator, everit json-schema, accepts only Integer/Long/BigInteger for
`"type": "integer"`, so a double such as `30.0` would fail. Typing integer slots as `number`
lets fractional counts through. Keep `range: integer` in the model for its meaning.

## Enum values with descriptions become oneOf/const

RJSF, which renders the Curator forms, only reads per-value metadata from `oneOf` entries
with a `const`. An enum without any value descriptions stays a plain `enum`.

## Registration versions

`curator-register` takes its version from the model's `version:`. A version that already
exists for any class stops the whole run before anything is stored, so a release is a
deliberate bump of `version:` and every class shares one version.
