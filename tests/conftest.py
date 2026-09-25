import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA_DIR = FIXTURES / "namhub"
EXPECTED = FIXTURES / "expected"


@pytest.fixture(scope="session")
def generated(tmp_path_factory) -> Path:
    """Build the CSV and JSON schemas from the fixture model into a temp directory.

    The scripts read "portal_schemas/" relative to the working directory, so the
    fixture schemas are linked in under that name.
    """
    out = tmp_path_factory.mktemp("generated")
    (out / "portal_schemas").symlink_to(SCHEMA_DIR)
    for module, args in (
        ("linkml_to_curator.datamodel_csv", ["--output", "namhub.model.csv"]),
        ("linkml_to_curator.generator", ["--source", "namhub.model.csv", "--output", "json"]),
    ):
        subprocess.run([sys.executable, "-m", module, *args], cwd=out, check=True,
                       capture_output=True)
    return out


@pytest.fixture(scope="session")
def schemas(generated) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text()) for p in (generated / "json").glob("*.json")}
