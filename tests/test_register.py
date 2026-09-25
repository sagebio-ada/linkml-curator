import json

import click
import pytest

from linkml_to_curator.register import register, resolve_version

SCHEMA = """
id: https://example.org/test
name: test
version: 2.3.0
"""


class FakeService:
    def __init__(self, registered: dict[str, list[str]] | None = None):
        self.registered = registered or {}
        self.created = []

    def list_json_schema_versions(self, org, name):
        return [{"semanticVersion": v} for v in self.registered.get(name, [])]

    def create_json_schema(self, schema, dry_run=False):
        self.created.append((schema["$id"], dry_run))


@pytest.fixture
def schema_dir(tmp_path):
    for name in ("Grants", "Landscape"):
        (tmp_path / f"{name}.json").write_text(json.dumps({"$id": "http://example.com/x"}))
    return tmp_path


def test_version_comes_from_schema(tmp_path):
    (tmp_path / "s.yaml").write_text(SCHEMA)
    assert resolve_version(None, str(tmp_path / "s.yaml")) == "2.3.0"
    assert resolve_version("9.0.0", str(tmp_path / "s.yaml")) == "9.0.0"


def test_missing_version_is_an_error(tmp_path):
    (tmp_path / "s.yaml").write_text(SCHEMA.replace("version: 2.3.0", ""))
    with pytest.raises(click.UsageError, match="declares no version"):
        resolve_version(None, str(tmp_path / "s.yaml"))


def test_registers_each_class(schema_dir):
    service = FakeService()
    ids = register(service, schema_dir, "NAMhub", "1.0.0", dry_run=True)
    assert ids == ["NAMhub-Grants-1.0.0", "NAMhub-Landscape-1.0.0"]
    assert service.created == [(i, True) for i in ids]


def test_existing_version_stops_before_registering(schema_dir):
    service = FakeService({"Landscape": ["0.9.0", "1.0.0"]})
    with pytest.raises(click.ClickException, match="already registered in NAMhub for: Landscape"):
        register(service, schema_dir, "NAMhub", "1.0.0", dry_run=False)
    assert service.created == []
