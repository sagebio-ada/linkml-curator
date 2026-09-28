# linkml-to-curator

Turn a [LinkML](https://linkml.io) data model into the JSON schemas that
[Synapse](https://www.synapse.org) Curator uses, and register those schemas with a Synapse
organization.

>[!WARNING]
>This tool is **still in early development** at Sage Bionetworks. Bug reports and questions are welcome in the [issue tracker](https://github.com/sagebio-ada/linkml-to-curator/issues).

The tool has three commands:

- `curator-lint` checks your LinkML model for things Curator or Synapse will reject.
- `gen-curator` reads your LinkML model and writes one JSON schema file per class.
- `curator-register` takes a folder of those JSON files and registers each one with Synapse.

## Setup

* **uv**, which installs and runs Python tools. One-line installation in the
[uv installation guide](https://docs.astral.sh/uv/getting-started/installation/). Every command
in this README that starts with `uv run` uses it.

**A Synapse access token**, for registering schemas, but not generating them. The script looks for a `SYNAPSE_AUTH_TOKEN` environment variable or a `.synapseConfig` file in your home folder:

```ini
[authentication]
authtoken = paste-your-token-here
```


## Installing

Once your LinkML project is configured to use this generator, all these commands
will be available by running `uv sync`.

To add this to your project, open a terminal in the root of your LinkML project and run:

```bash
uv add --dev "linkml-to-curator @ git+https://github.com/sagebio-ada/linkml-to-curator"
```

That records the tool as a dependency of the project, so anyone else who clones the project gets
it with `uv sync` afterward.

## Checking the model

`curator-lint` reads the model and reports what would stop generation or registration, or what
Synapse would reject once registered:

```bash
uv run curator-lint src/namhub/schema/namhub.yaml
```

Each line names the class, slot or enum and what is wrong with it, and the command exits with
an error status if there are any errors. Some examples:

- A constraint that doesn't fit the slot's type, the same check `gen-curator` makes
- LinkML names that would become the same Curator property, such as `datasetId` and
  `dataset_id`
- A `pattern` that doesn't compile, or that uses Python's `(?P<name>)` group syntax, which the
  Java regex engine on Synapse doesn't read. Write `(?<name>)`;
- Broken lists: an enum with no values, a value that is empty or has whitespace around it, or two values that
  differ only by case or punctuation, such as `RNA-seq` and `rna seq`;
- A `slot_usage` entry naming a slot the class doesn't have, or a `range` that isn't a type,
  class or enum. (LinkML accepts both, but these will cause problems for us.)

Pass `--strict` to fail on warnings too. The check suits a project's test recipe or CI, see
[Running it automatically](#running-it-automatically).

## Generating schemas

Point `gen-curator` at the model file and name a folder for the output:

```bash
uv run gen-curator src/namhub/schema/namhub.yaml -d project/curator
```

That writes one file per class, such as `project/curator/Landscape.json`, and creates the folder
if it doesn't exist. The class name is the file name. To look at one class without writing any
files, name it with `-t` and the JSON prints to the terminal:

```bash
uv run gen-curator src/namhub/schema/namhub.yaml -t Landscape
```

If a model file imports others, as `namhub.yaml` imports `enums.yaml`, name only the main file.
The imports are followed automatically.

Generation stops with an error when a constraint doesn't fit the slot's type: `pattern` needs a
string range, and `minimum_value`/`maximum_value` need a numeric one. Neither applies to enums.

## Registering schemas

Once the JSON files look right, register them. Do a dry run first, which has Synapse check the
schemas without storing anything:

```bash
uv run curator-register project/curator --org NAMhub --schema src/namhub/schema/namhub.yaml --dry-run
```

The parts of that command:

- `project/curator` is the folder that `gen-curator` wrote.
- `--org NAMhub` is the Synapse organization to register under.
- `--schema src/namhub/schema/namhub.yaml` is the model, read only for its `version:` line.
- `--dry-run` validates without storing. Leave it off to register for real.

Each file is registered as `<org>-<Class>-<version>`, for example `NAMhub-Landscape-1.2.0`, and
the command prints each name as it goes.

### Versions

Every class shares one version, taken from the `version:` line at the top of the model:

```yaml
id: https://namhub.synapse.org/portal_schemas
name: namhub
version: 1.2.0
```

If any class in the folder already has that version in the organization, nothing is registered
and the command tells you which classes are taken. So releasing a new set of schemas means
changing `version:` in the model, regenerating, and registering. To register under a version
other than the model's, pass `--version 1.2.1` instead of `--schema`.

## Running it automatically

Both commands can run from a project's task runner or from GitHub Actions, so the schemas stay
in step with the model.

In a [linkml-project-copier](https://github.com/linkml/linkml-project-copier) project, add
recipes to `project.justfile` so that `uv run just lint-curator` checks the model and
`uv run just gen-curator` regenerates the schemas:

```just
# Check the model against what Curator and Synapse accept
lint-curator:
  uv run curator-lint {{source_schema_path}}

# Generate Synapse Curator JSON schemas
gen-curator:
  uv run gen-curator -d {{dest}}/curator {{source_schema_path}}
```

In GitHub Actions, store the Synapse token as a repository secret named `SYNAPSE_AUTH_TOKEN`
and add these steps to a workflow:

```yaml
- run: uv run just lint-curator
- run: uv run just gen-curator
- run: uv run curator-register project/curator --org NAMhub --schema src/namhub/schema/namhub.yaml
  env:
    SYNAPSE_AUTH_TOKEN: ${{ secrets.SYNAPSE_AUTH_TOKEN }}
```

## What the generator writes

Every class that is not abstract or a mixin becomes a draft-07 JSON schema. For each one:

- slots, inherited ones included, become properties keyed by PascalCase slot name
  (`datasetAssay` and `dataset_assay` → `DatasetAssay`);
- a property's title is the slot's LinkML `title:`, or else one derived from the slot name
  (`uploadByDate` → `Upload By Date`, `landscapeId` → `Landscape_id`);
- enum values are sorted, and if any value has a description they become `oneOf` entries
  with `const`, `title` and `description`;
- `integer`, `float`, `double` and `decimal` are typed `number`; `date`, `datetime` and `uri`
  are strings with a `format`;
- multivalued slots are arrays of the single-value schema;
- `required` lists the slots that class requires;
- `$id` is a placeholder, which `curator-register` replaces.

## When something goes wrong

**`No valid authentication credentials provided`** means `curator-register` found no Synapse
token. Check that `.synapseConfig` is in your home folder and has the two lines shown above, or
that `SYNAPSE_AUTH_TOKEN` is set in the terminal you are using.

**`declares no version; set one or pass --version`** means the model has no `version:` line.
Add one, or pass `--version`.

**`Version 1.2.0 is already registered in NAMhub for: Landscape, Studies`** means those classes
have that version already. Bump `version:` in the model and regenerate.

**`Directory 'project/curator' does not exist`** or **`No JSON schemas in project/curator`**
means there is nothing to register. Run `gen-curator` first, and check that both commands name
the same folder.

**`command not found: uv`** means uv isn't installed, or the terminal was opened before it was
installed. Open a new terminal window and try again.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
