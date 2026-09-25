from linkml_to_curator.generator import restore_titles


def test_linkml_title_wins_over_derived_title():
    schema = {"properties": {"A": {"title": "datasetAssay"}, "B": {"title": "landscapeId"}}}
    restore_titles(schema, {"datasetAssay": "Assay", "landscapeId": None})
    assert schema["properties"]["A"]["title"] == "Assay"
    assert schema["properties"]["B"]["title"] == "Landscape_id"
