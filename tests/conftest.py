import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from linkml_to_curator.generator import cli

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA = FIXTURES / "namhub" / "namhub.yaml"
EXPECTED = FIXTURES / "expected"


@pytest.fixture(scope="session")
def generated(tmp_path_factory) -> Path:
    """Generate the JSON schemas for the fixture model into a temp directory."""
    out = tmp_path_factory.mktemp("generated")
    result = CliRunner().invoke(cli, [str(SCHEMA), "-d", str(out)])
    assert result.exit_code == 0, result.output
    return out


@pytest.fixture(scope="session")
def schemas(generated) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text()) for p in generated.glob("*.json")}
