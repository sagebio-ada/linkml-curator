"""Register generated Curator JSON schemas with a Synapse organization.

Each DIR/<Class>.json is registered as <org>-<Class>-<version>. The version is
--version if given, else the LinkML schema's `version:`. Registration stops before
storing anything if any class already has that version, so the model's
`version:` has to be bumped on purpose.

Synapse credentials come from the usual synapseclient sources, such as the
SYNAPSE_AUTH_TOKEN environment variable or ~/.synapseConfig.

Usage:
    curator-register DIR --org NAMhub --schema schema.yaml [--version 1.2.0] [--dry-run]
"""

import json
from importlib.metadata import version as package_version
from pathlib import Path

import click
from linkml_runtime import SchemaView
from synapseclient.core.exceptions import SynapseHTTPError


def resolve_version(version: str | None, schema_path: str | None) -> str:
    if version:
        return version
    if not schema_path:
        raise click.UsageError("Pass --version, or --schema to read the LinkML schema's version.")
    schema_version = SchemaView(schema_path).schema.version
    if not schema_version:
        raise click.UsageError(f"{schema_path} declares no version; set one or pass --version.")
    return schema_version


def registered_versions(service, org: str, name: str) -> set[str]:
    try:
        versions = list(service.list_json_schema_versions(org, name))
    except SynapseHTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return set()
        raise
    return {v["semanticVersion"] for v in versions if v.get("semanticVersion")}


def register(service, directory: Path, org: str, version: str, dry_run: bool) -> list[str]:
    """Register every <Class>.json in directory at version; return the registered $ids."""
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise click.UsageError(f"No JSON schemas in {directory}.")

    taken = [p.stem for p in paths if version in registered_versions(service, org, p.stem)]
    if taken:
        raise click.ClickException(
            f"Version {version} is already registered in {org} for: {', '.join(taken)}."
        )

    ids = []
    for path in paths:
        schema = json.loads(path.read_text())
        schema["$id"] = f"{org}-{path.stem}-{version}"
        service.create_json_schema(schema, dry_run=dry_run)
        click.echo(f"{'[dry-run] ' if dry_run else ''}Registered {schema['$id']}")
        ids.append(schema["$id"])
    return ids


@click.command()
@click.version_option(package_version("linkml-to-curator"), "-V", "--version-info")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--org", required=True, help="Synapse organization, e.g. NAMhub.")
@click.option("--schema", type=click.Path(exists=True, dir_okay=False),
              help="LinkML schema whose `version:` sets the registered version.")
@click.option("--version", help="Version to register, overriding the schema's.")
@click.option("--dry-run", is_flag=True, help="Have Synapse validate without storing.")
def cli(directory: Path, org: str, schema: str | None, version: str | None, dry_run: bool):
    """Register each <Class>.json in DIRECTORY with a Synapse organization."""
    import synapseclient
    from synapseclient.services.json_schema import JsonSchemaService

    version = resolve_version(version, schema)
    syn = synapseclient.Synapse()
    syn.login(silent=True)
    register(JsonSchemaService(synapse=syn), directory, org, version, dry_run)


if __name__ == "__main__":
    cli()
