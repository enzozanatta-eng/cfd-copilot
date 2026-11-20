import pytest
from pydantic import ValidationError

from cfdcopilot.spec import CavitySpec, dump_spec, parse_spec


def test_valid_spec_roundtrip():
    spec = CavitySpec(name="cav", reynolds=100, cells=64)
    import yaml

    assert parse_spec(yaml.safe_load(dump_spec(spec))) == spec
    assert spec.nu == pytest.approx(0.01)


def test_rejects_unsteady_reynolds():
    with pytest.raises(ValidationError, match="transient"):
        CavitySpec(name="cav", reynolds=10_000, cells=512)


def test_rejects_too_coarse_mesh():
    with pytest.raises(ValidationError, match="too coarse"):
        CavitySpec(name="cav", reynolds=1000, cells=64)


def test_rejects_bad_name():
    with pytest.raises(ValidationError):
        CavitySpec(name="has spaces", reynolds=100)
