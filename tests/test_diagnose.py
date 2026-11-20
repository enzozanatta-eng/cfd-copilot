from cfdcopilot.diagnose import diagnose, diagnose_or_tail


def test_divergence(fixture_text):
    titles = [d.title for d in diagnose(fixture_text("foamRun_fpe.log"))]
    assert "Solution diverged" in titles


def test_reference_cell_names_the_field(fixture_text):
    (d,) = diagnose(fixture_text("foamRun_pref.log"))
    assert d.title == "Pressure level undefined"
    assert "'p'" in d.cause
    assert "pRefCell" in d.fix


def test_missing_keyword_is_specific():
    log = 'Keyword nOuterCorrectors is undefined in dictionary "system/fvSolution/PIMPLE"'
    (d,) = diagnose(log)
    assert "nOuterCorrectors" in d.cause and "fvSolution" in d.cause


def test_clean_log_has_no_diagnosis(fixture_text):
    assert diagnose(fixture_text("foamRun_converged.log")) == []


def test_sigfpe_banner_is_not_a_crash():
    # OpenFOAM prints this in every log header; it is not an error.
    banner = "sigFpe : Enabling floating point exception trapping (FOAM_SIGFPE)."
    assert diagnose(banner) == []


def test_unknown_failure_shows_log_tail():
    (d,) = diagnose_or_tail("line 1\nsomething odd happened\n")
    assert d.title == "Unrecognised failure"
    assert "something odd happened" in d.evidence


def test_dictionary_as_primitive_names_the_entry(fixture_text):
    (d,) = diagnose(fixture_text("foamRun_dict_primitive.log"))
    assert d.title == "Wrong dictionary structure"
    assert "centreline/sets" in d.cause
