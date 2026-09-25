from click.testing import CliRunner

from conftest import EXPECTED, SCHEMA
from linkml_to_curator.generator import cli


def test_top_class_prints_one_schema():
    result = CliRunner().invoke(cli, [str(SCHEMA), "-t", "Grants"])
    assert result.exit_code == 0, result.output
    assert result.output == (EXPECTED / "Grants.json").read_text() + "\n"


def test_several_classes_need_a_directory():
    result = CliRunner().invoke(cli, [str(SCHEMA)])
    assert result.exit_code != 0
    assert "--directory" in str(result.exception)


def test_unknown_top_class():
    result = CliRunner().invoke(cli, [str(SCHEMA), "-t", "Nope"])
    assert "not a template class" in str(result.exception)


def test_csv_output_is_the_data_model_verbatim():
    result = CliRunner().invoke(cli, [str(SCHEMA), "-f", "csv"])
    assert result.exit_code == 0, result.output
    assert result.stdout_bytes == (EXPECTED / "namhub.model.csv").read_bytes()
