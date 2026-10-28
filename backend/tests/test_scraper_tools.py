"""Scraper tools and PDF preparation, tested without network: a fake Firecrawl client and a mock HTTP transport."""

import asyncio

import httpx
import pymupdf
import pytest
from firecrawl.v2.types import BrandingProfile, Document, DocumentMetadata

from app.scraper.tools import (
    MAX_IMAGES,
    MAX_PDF_PAGES,
    build_scraper_tools,
    download_images,
    prepare_pdf,
    website_image_urls,
)
from app.storage.brands import BrandStore


def png(width: int, height: int) -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False)
    pixmap.clear_with(200)
    return pixmap.tobytes("png")


def fake_web(request: httpx.Request) -> httpx.Response:
    """Every URL is a PNG, except two: one missing, one that is a web page."""
    if request.url.path == "/missing.png":
        return httpx.Response(404)
    if request.url.path == "/page.html":
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html></html>")
    return httpx.Response(200, headers={"content-type": "image/png"}, content=png(10, 10))


def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(fake_web))


class FakeFirecrawl:
    """Returns a fixed page, or raises if `error` is set. Remembers the options it got."""

    def __init__(self, page: Document | None = None, error: Exception | None = None):
        self.page, self.error, self.calls = page, error, []

    async def scrape(self, url, **options):
        self.calls.append(options)
        if self.error:
            raise self.error
        return self.page


ACME_PAGE = Document(
    markdown="# Acme\nBold shoes for bold people.",
    raw_html="<html><body><h1>Acme</h1></body></html>",
    images=["https://acme.com/hero.png", "https://acme.com/logo.png", "https://acme.com/missing.png"],
    screenshot="https://firecrawl.dev/shots/acme.png",
    metadata=DocumentMetadata(title="Acme shoes"),
    branding=BrandingProfile(
        brand_name="Acme",
        logo="https://acme.com/logo.png",
        colors={"primary": "#E4002B"},
        images={"favicon": "data:image/png;base64,AAAA"},
    ),
)


@pytest.fixture
def brand_dir(tmp_path):
    store = BrandStore(tmp_path)
    return store.brand_dir(store.create_brand())


def test_image_urls_put_the_logo_first_without_duplicates_or_inline_data():
    assert website_image_urls(ACME_PAGE) == [
        "https://acme.com/logo.png",
        "https://acme.com/hero.png",
        "https://acme.com/missing.png",
    ]


def test_download_images_skips_what_is_not_an_image_and_stops_at_the_limit(tmp_path):
    urls = ["https://x.com/missing.png", "https://x.com/page.html"]
    urls += [f"https://x.com/{n}.png" for n in range(MAX_IMAGES + 5)]

    async def run():
        async with http_client() as http:
            return await download_images(urls, tmp_path, http)

    saved = asyncio.run(run())
    assert len(saved) == MAX_IMAGES
    assert saved[0] == ("image-01.png", "https://x.com/0.png")
    assert len(list(tmp_path.iterdir())) == MAX_IMAGES


def test_scrape_website_saves_files_and_returns_a_short_summary(brand_dir):
    firecrawl = FakeFirecrawl(page=ACME_PAGE)

    async def run():
        async with http_client() as http:
            (scrape_website,) = build_scraper_tools(brand_dir, firecrawl, http)
            return await scrape_website.ainvoke({"url": "https://acme.com"})

    summary = asyncio.run(run())

    for name in ("branding.json", "page.md", "page.html", "screenshot.png"):
        assert (brand_dir / "raw" / name).exists()
    assert "#E4002B" in summary
    assert "/assets/image-01.png -> https://acme.com/logo.png" in summary
    assert "missing.png" not in summary  # the 404 was skipped
    assert firecrawl.calls[0]["only_main_content"] is False  # keep header and footer


def test_scrape_website_returns_a_message_when_firecrawl_fails(brand_dir):
    firecrawl = FakeFirecrawl(error=RuntimeError("timeout"))

    async def run():
        async with http_client() as http:
            (scrape_website,) = build_scraper_tools(brand_dir, firecrawl, http)
            return await scrape_website.ainvoke({"url": "https://acme.com"})

    assert asyncio.run(run()) == "Could not read https://acme.com: timeout"


def make_pdf(path, pages: int):
    """A PDF whose first page holds a large logo and a small icon."""
    pdf = pymupdf.open()
    for number in range(pages):
        page = pdf.new_page()
        page.insert_text((72, 72), f"Acme brand guide, page {number + 1}.")
    pdf[0].insert_image(pymupdf.Rect(72, 100, 272, 300), stream=png(200, 200))  # logo: kept
    pdf[0].insert_image(pymupdf.Rect(72, 320, 92, 340), stream=png(20, 20))  # icon: skipped
    pdf.save(path)


def test_prepare_pdf_saves_page_images_and_only_the_large_embedded_images(brand_dir):
    make_pdf(brand_dir / "uploads" / "guide.pdf", pages=2)

    pdf = prepare_pdf(brand_dir / "uploads" / "guide.pdf", brand_dir / "raw", brand_dir / "assets")

    assert pdf.page_count == 2
    assert pdf.page_images == ["guide-page-1.png", "guide-page-2.png"]
    assert (brand_dir / "raw" / "guide-page-1.png").exists()
    assert pdf.image_files == ["guide-1.png"]
    assert [p.name for p in (brand_dir / "assets").iterdir()] == ["guide-1.png"]


def test_prepare_pdf_stops_rendering_pages_at_the_limit(brand_dir):
    make_pdf(brand_dir / "uploads" / "long.pdf", pages=MAX_PDF_PAGES + 3)

    pdf = prepare_pdf(brand_dir / "uploads" / "long.pdf", brand_dir / "raw", brand_dir / "assets")

    assert pdf.page_count == MAX_PDF_PAGES + 3
    assert len(pdf.page_images) == MAX_PDF_PAGES


def test_the_model_sees_a_description_for_the_url(brand_dir):
    (scrape_website,) = build_scraper_tools(brand_dir, FakeFirecrawl(), http_client())
    assert "http://" in scrape_website.args["url"]["description"]
