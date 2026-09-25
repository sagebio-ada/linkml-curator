# linkml-to-curator

Generate Synapse Curator JSON schemas from a LinkML model, and register them with a
Synapse organization.

- `gen-curator` is a LinkML generator. It takes the same options as the built-in `gen-*`
  tools and writes one JSON schema per template class. It makes no network calls.
- `curator-register` registers a directory of those schemas with a Synapse organization.

## Installation

Add it to the LinkML project that holds your model:

```bash
uv add --dev "linkml-to-curator @ git+https://github.com/sagebio-ada/linkml-to-curator"
```

## Generating schemas

```bash
gen-curator schema.yaml -d project/curator   # one <Class>.json per template class
gen-curator schema.yaml -t Landscape         # one class, to stdout
gen-curator schema.yaml -f csv               # the intermediate Curator data-model CSV
```

Every class that is not abstract or a mixin becomes a template. For each one:

- slots become properties keyed by Curator's PascalCase node label (`datasetAssay` →
  `DatasetAssay`);
- enum values keep their spaces, and values with a description become `oneOf` entries with
  `const`, `title` and `description`;
- a property's title is the slot's LinkML `title:`, or else one derived from the slot name
  (`uploadByDate` → `Upload By Date`, `landscapeId` → `Landscape_id`);
- `required` lists the slots that class requires;
- `integer` slots are typed `number`.

A slot shared by several classes has to agree across them on range, multivalued, pattern
and bounds, because Curator's data model has one row per slot. `required` may differ.

In a [linkml-project-copier](https://github.com/linkml/linkml-project-copier) project, add a
recipe to `project.justfile`:

```just
# Generate Synapse Curator JSON schemas
gen-curator:
  uv run gen-curator -d {{dest}}/curator {{source_schema_path}}
```

## Registering schemas

```bash
curator-register project/curator --org NAMhub --schema src/namhub/schema/namhub.yaml --dry-run
```

Each `<Class>.json` is registered as `<org>-<Class>-<version>`. The version is the LinkML
schema's `version:`, or `--version` if given. If any class already has that version in the
organization, nothing is registered, so a release means bumping `version:` in the model.
`--dry-run` has Synapse validate the schemas without storing them.

Credentials come from synapseclient's usual sources. In GitHub Actions, set
`SYNAPSE_AUTH_TOKEN`:

```yaml
- run: uv run just gen-curator
- run: uv run curator-register project/curator --org NAMhub --schema src/namhub/schema/namhub.yaml
  env:
    SYNAPSE_AUTH_TOKEN: ${{ secrets.SYNAPSE_AUTH_TOKEN }}
```

## Development

```bash
uv sync
uv run pytest
uv run ruff check
```

`tests/fixtures/namhub/` is the NAMhub model, and `tests/fixtures/expected/` is the
generator's output for it. A change to `expected/` is a change to the output. Regenerate it
and review the diff:

```bash
uv run gen-curator tests/fixtures/namhub/namhub.yaml -d tests/fixtures/expected
uv run gen-curator tests/fixtures/namhub/namhub.yaml -f csv > tests/fixtures/expected/namhub.model.csv
```
