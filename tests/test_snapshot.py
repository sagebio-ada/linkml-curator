"""The generated JSON schemas match the snapshot in tests/fixtures/expected/.

A change to expected/ is a change to the generator's output and should be deliberate.
"""

import pytest

from conftest import EXPECTED

EXPECTED_JSON = sorted(p.name for p in EXPECTED.glob("*.json"))


def test_one_schema_per_class(generated):
    assert sorted(p.name for p in generated.glob("*.json")) == EXPECTED_JSON


@pytest.mark.parametrize("name", EXPECTED_JSON)
def test_json_schema(generated, name):
    assert (generated / name).read_text() == (EXPECTED / name).read_text()
