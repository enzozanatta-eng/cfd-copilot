from cfdcopilot.cli import EXIT_BAD_SPEC, EXIT_OK, main


def test_new_and_validate(tmp_path, capsys):
    spec = tmp_path / "cav.yaml"
    assert main(["new", "--name", "cav", "--re", "100", "-o", str(spec)]) == EXIT_OK
    assert main(["validate", str(spec)]) == EXIT_OK


def test_new_rejects_bad_physics(capsys):
    assert main(["new", "--name", "cav", "--re", "1000", "--cells", "32"]) == EXIT_BAD_SPEC
    assert "too coarse" in capsys.readouterr().err


def test_build_writes_case(tmp_path):
    spec = tmp_path / "cav.yaml"
    main(["new", "--name", "cav", "--re", "100", "-o", str(spec)])
    assert main(["build", str(spec), "-o", str(tmp_path / "runs")]) == EXIT_OK
    assert (tmp_path / "runs/cav/system/blockMeshDict").is_file()
