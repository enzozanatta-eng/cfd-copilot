from cfdcopilot.foam.logs import parse_checkmesh, parse_solver_log


def test_parse_converged_run(fixture_text):
    log = parse_solver_log(fixture_text("foamRun_converged.log"))
    assert log.finished
    assert log.converged_at == 300
    assert log.iterations == 300
    assert set(log.residuals) == {"Ux", "Uy", "p"}
    assert len(log.residuals["p"]) == 300
    assert log.residual_drop("p") > 5
    assert log.fatal_error is None


def test_parse_fatal(fixture_text):
    log = parse_solver_log(fixture_text("foamRun_pref.log"))
    assert not log.finished
    assert "reference cell" in log.fatal_error


def test_parse_checkmesh(fixture_text):
    rep = parse_checkmesh(fixture_text("checkMesh_ok.log"))
    assert rep.mesh_ok
    assert rep.cells == 4096
    assert rep.max_non_orthogonality == 0
    assert rep.max_aspect_ratio == 6.4
