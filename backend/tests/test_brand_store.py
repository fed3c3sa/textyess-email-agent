import pytest
from pydantic import ValidationError

from app.schemas.design_system import ColorToken, DesignSystem, Identity
from app.storage.brands import BrandStore


@pytest.fixture
def store(tmp_path):
    return BrandStore(tmp_path)


@pytest.fixture
def brand_id(store):
    return store.create_brand()


def test_create_brand_makes_the_subfolders(store, brand_id):
    folder = store.brand_dir(brand_id)
    assert {p.name for p in folder.iterdir()} == {"assets", "raw", "uploads"}


@pytest.mark.parametrize("bad_id", ["../etc", "nope", "deadbeef"])
def test_unknown_or_tricky_brand_id_is_rejected(store, bad_id):
    with pytest.raises(FileNotFoundError):
        store.brand_dir(bad_id)


def test_load_is_none_before_the_first_save(store, brand_id):
    assert store.load(brand_id) is None


def test_save_then_load_round_trip(store, brand_id):
    ds = DesignSystem(identity=Identity(name="Acme"))
    store.save(brand_id, ds)
    assert store.load(brand_id) == ds


def test_re_scrape_keeps_the_saved_notes(store, brand_id):
    store.save(brand_id, DesignSystem(identity=Identity(name="Old")))
    store.add_note(brand_id, "no emojis in subject lines")

    store.save(brand_id, DesignSystem(identity=Identity(name="New"), user_notes=["from the scraper"]))

    saved = store.load(brand_id)
    assert saved.identity.name == "New"
    assert saved.user_notes == ["no emojis in subject lines"]


def test_add_note_works_before_any_scrape(store, brand_id):
    store.add_note(brand_id, "keep it short")
    assert store.load(brand_id).user_notes == ["keep it short"]


def test_update_nested_field(store, brand_id):
    store.save(brand_id, DesignSystem())
    updated = store.update_field(brand_id, "identity.name", "Acme")
    assert updated.identity.name == "Acme"
    assert store.load(brand_id).identity.name == "Acme"


def test_update_list_field_replaces_it_whole(store, brand_id):
    store.save(brand_id, DesignSystem(colors=[ColorToken(role="primary", hex="#000000")]))
    updated = store.update_field(brand_id, "colors", [{"role": "cta", "hex": "#E4002B"}])
    assert updated.colors == [ColorToken(role="cta", hex="#E4002B")]


@pytest.mark.parametrize("path", ["nope", "identity.nope", "guidelines.deeper"])
def test_update_unknown_path_raises(store, brand_id, path):
    with pytest.raises(ValueError):
        store.update_field(brand_id, path, "x")


def test_update_with_wrong_shape_raises_and_saves_nothing(store, brand_id):
    store.save(brand_id, DesignSystem())
    with pytest.raises(ValidationError):
        store.update_field(brand_id, "colors", [{"role": "cta"}])  # hex is missing
    assert store.load(brand_id).colors == []
