from cfdcopilot.foam.dicts import Raw, foam_file


def test_foam_file_syntax():
    text = foam_file("dictionary", "test", {
        "a": 1,
        "flag": True,
        "vec": (1, 0, 0),
        "dims": Raw("[0 1 -1 0 0 0 0]"),
        "sub": {"x": 0.5},
    }, location="system")
    assert "class            dictionary;" in text
    assert 'location         "system";' in text
    assert "flag             yes;" in text
    assert "vec              (1 0 0);" in text
    assert "dims             [0 1 -1 0 0 0 0];" in text
    assert "sub\n{\n    x                0.5;\n}" in text
    assert text.count("{") == text.count("}")
