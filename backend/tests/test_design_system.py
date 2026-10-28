import pytest
from pydantic import ValidationError

from app.schemas.design_system import Asset, DesignSystem, ScrapeResult


def test_empty_design_system_is_valid():
    """A sparse website may fill nothing: every field has a default."""
    ds = DesignSystem()
    assert ds.colors == []
    assert ds.email_constraints == []


def test_json_round_trip():
    ds = DesignSystem.model_validate(
        {
            "identity": {"name": "Acme"},
            "colors": [{"role": "primary", "hex": "#E4002B"}],
            "user_notes": ["no emojis in subject lines"],
        }
    )
    assert DesignSystem.model_validate_json(ds.model_dump_json()) == ds


def test_asset_role_is_restricted():
    with pytest.raises(ValidationError):
        Asset(description="x", role="banner", pointer="a.png")


def test_scrape_result_defaults_to_no_conflicts():
    assert ScrapeResult(design_system=DesignSystem()).conflicts == []
