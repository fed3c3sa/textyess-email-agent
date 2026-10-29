"""The scraper's flow, tested without a model: a fake agent stands in for create_agent."""

import asyncio
import base64
import io

from PIL import Image

from app.config import MAX_IMAGE_WIDTH, MAX_IMAGES_TO_MODEL, Settings
from app.schemas.design_system import Conflict, DesignSystem, Identity, ScrapeResult
from app.agents.scraper import agent as scraper_agent
from app.agents.scraper.agent import build_first_message, image_block, scrape_brand
from tests.conftest import make_pdf, png


def labels(message) -> list[str]:
    """The path labels written before each image, in order."""
    return [block["text"] for block in message.content[1:] if block["type"] == "text"]


def test_first_message_has_the_text_then_every_image_after_its_path(brand_dir):
    (brand_dir / "raw" / "screenshot.png").write_bytes(png(10, 10))
    (brand_dir / "raw" / "guide-page-1.png").write_bytes(png(10, 10))
    (brand_dir / "raw" / "page.md").write_text("# Acme")  # text, not attached
    (brand_dir / "uploads" / "guide.pdf").write_bytes(b"%PDF")  # listed, not attached
    (brand_dir / "uploads" / "logo.png").write_bytes(png(10, 10))
    (brand_dir / "assets" / "image-01.png").write_bytes(png(10, 10))
    (brand_dir / "assets" / "icon.svg").write_text("<svg/>")  # models cannot see SVG

    message = build_first_message(brand_dir, "https://acme.com", "Read https://acme.com.", None)

    text = message.content[0]["text"]
    assert "https://acme.com" in text
    assert "/uploads/guide.pdf" in text
    assert "Nothing yet." in text
    assert labels(message) == [
        "/raw/guide-page-1.png:",
        "/raw/screenshot.png:",
        "/uploads/logo.png:",
        "/assets/image-01.png:",
    ]
    assert message.content[2] == {"type": "image", "base64": message.content[2]["base64"], "mime_type": "image/png"}


def test_first_message_carries_what_we_already_know(brand_dir):
    current = DesignSystem(identity=Identity(name="Acme"))
    message = build_first_message(brand_dir, None, "No website was given.", current)
    assert '"name": "Acme"' in message.content[0]["text"]


def test_wide_images_are_shrunk(tmp_path):
    path = tmp_path / "wide.png"
    path.write_bytes(png(3000, 1000))

    block = image_block(path)

    width = Image.open(io.BytesIO(base64.b64decode(block["base64"]))).width
    assert width <= MAX_IMAGE_WIDTH


def test_webp_images_are_read(tmp_path):
    """Many shops serve their images as WebP."""
    path = tmp_path / "photo.webp"
    Image.new("RGB", (50, 50), "red").save(path, format="WEBP")
    assert image_block(path)["mime_type"] == "image/png"


def test_first_message_stops_at_the_image_limit(brand_dir):
    for number in range(MAX_IMAGES_TO_MODEL + 5):
        (brand_dir / "assets" / f"image-{number:02d}.png").write_bytes(png(10, 10))

    message = build_first_message(brand_dir, None, "No website was given.", None)

    assert len(labels(message)) == MAX_IMAGES_TO_MODEL


def test_a_broken_image_is_skipped(tmp_path):
    path = tmp_path / "broken.png"
    path.write_bytes(b"not an image")
    assert image_block(path) is None


class FakeAgent:
    """Returns a fixed result (None: it ran out of model calls) and remembers the message it got."""

    def __init__(self, result: ScrapeResult | None):
        self.result, self.messages = result, []

    async def ainvoke(self, state):
        self.messages.extend(state["messages"])
        return {"structured_response": self.result, "messages": state["messages"]}


class FakeModel:
    """Stands in for ChatOpenRouter: its structured output returns a fixed result."""

    def __init__(self, result: ScrapeResult):
        self.result = result

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        return self.result


def test_scrape_brand_prepares_the_pdf_runs_the_agent_and_saves(store, brand_id, brand_dir, monkeypatch):
    make_pdf(brand_dir / "uploads" / "guide.pdf", pages=1)
    store.add_note(brand_id, "no emojis")
    result = ScrapeResult(
        design_system=DesignSystem(identity=Identity(name="Acme")),
        conflicts=[Conflict(field="colors", website_value="#D0021B", document_value="#E4002B")],
    )
    fake = FakeAgent(result)
    monkeypatch.setattr(scraper_agent, "create_agent", lambda **kwargs: fake)
    settings = Settings(openrouter_api_key="test", firecrawl_api_key="test")
    reports = []

    returned = asyncio.run(scrape_brand(store, brand_id, None, settings, reports.append))

    assert "/raw/guide-page-1.png:" in labels(fake.messages[0])  # the PDF page reached the model
    assert returned.conflicts == result.conflicts
    saved = store.load(brand_id)
    assert saved.identity.name == "Acme"
    assert saved.user_notes == ["no emojis"]  # kept across the re-scrape
    assert reports == ["Reading the documents...", "Building the design system..."]


def test_scrape_brand_asks_for_the_answer_when_the_agent_runs_out_of_calls(store, brand_id, monkeypatch):
    result = ScrapeResult(design_system=DesignSystem(identity=Identity(name="Acme")))
    monkeypatch.setattr(scraper_agent, "create_agent", lambda **kwargs: FakeAgent(None))
    monkeypatch.setattr(scraper_agent, "ChatOpenRouter", lambda **kwargs: FakeModel(result))
    settings = Settings(openrouter_api_key="test", firecrawl_api_key="test")
    reports = []

    asyncio.run(scrape_brand(store, brand_id, None, settings, reports.append))

    assert store.load(brand_id).identity.name == "Acme"
    assert reports[-1] == "Writing the design system..."
