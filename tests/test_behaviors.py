"""Output properties that Synapse and the Curator grid depend on."""


def test_enum_values_keep_spaces(schemas):
    values = schemas["Landscape"]["properties"]["DatasetSpecies"]["enum"]
    assert "Homo sapiens" in values


def test_enum_value_descriptions_become_oneof_consts(schemas):
    one_of = schemas["Landscape"]["properties"]["DatasetProcessingLevel"]["oneOf"]
    level1 = next(v for v in one_of if v["const"] == "Level 1")
    assert level1["title"] == "Level 1"
    assert level1["description"] == "Raw or minimally processed data."


def test_property_keys_are_pascal_case(schemas):
    for schema in schemas.values():
        for key in schema["properties"]:
            assert key[0].isupper() and " " not in key, key
        for key in schema["required"]:
            assert key in schema["properties"], key


def test_integer_slots_are_numbers(schemas):
    assert schemas["Landscape"]["properties"]["ExpectedNumberOfFiles"]["type"] == "number"


def test_titles(schemas):
    props = schemas["Landscape"]["properties"]
    assert props["LandscapeId"]["title"] == "Landscape_id"
    assert props["UploadByDate"]["title"] == "Upload By Date"


def test_required_is_per_class(schemas):
    # studyId is required only by Studies' slot_usage, though Datasets uses it too.
    assert "StudyId" in schemas["Studies"]["required"]
    assert "StudyId" not in schemas["Datasets"]["required"]
    assert "StudyId" in schemas["Datasets"]["properties"]
