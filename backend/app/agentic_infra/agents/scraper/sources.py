"""The sources the scraper reads, gathered before it runs, without any model.

`read_website` asks Firecrawl for a page's branding, text, HTML, images and
screenshot, so no browser runs locally. `prepare_pdf` saves each page of a PDF as an
image and keeps the images found inside it (logos, photos). Everything is written
into the brand folder (`raw/`, `assets/`), where the scraper finds it.

Paths in the summary start with `/`, because the scraper's file tools see the brand
folder as their root.
"""

import logging
import json
from pathlib import Path

import httpx
import pymupdf
from firecrawl import AsyncFirecrawl

from app.config import MAX_IMAGES_TO_MODEL, MAX_PAGE_CHARS, MAX_PDF_PAGES, SUMMARY_TEXT_CHARS
from app.schemas.pdf import PdfContent

logger = logging.getLogger(__name__)

FIRECRAWL_FORMATS = ["branding", "markdown", "rawHtml", "images", "screenshot"]
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
PDF_PAGE_DPI = 110  # enough to read small text on a page
MIN_PDF_IMAGE_SIDE = 100


async def read_website(url: str, brand_dir: Path, firecrawl: AsyncFirecrawl, http: httpx.AsyncClient) -> str:
    """Read a website with Firecrawl, save what describes the brand, and return a short summary.

    Saves /raw/branding.json (colors, fonts, typography, button styles, logo and tone,
    measured on the live page), /raw/page.md (the visible text), /raw/page.html, a
    screenshot in /raw, and up to MAX_IMAGES_TO_MODEL images in /assets (logo first).
    The HTML and the text are cut at MAX_PAGE_CHARS characters. The summary gives
    the branding profile, the first lines of text, and each saved image with its
    original URL. If the site can't be read, the summary says so instead of raising.
    """
    raw_dir = brand_dir / "raw"
    logger.info("Reading %s with Firecrawl", url)
    try:
        page = await firecrawl.scrape(url, formats=FIRECRAWL_FORMATS, only_main_content=False)
    except Exception as error:
        logger.warning("Could not read %s: %s", url, error)
        return f"Could not read {url}: {error}"

    branding = without_inline_images(page.branding.model_dump(exclude_none=True)) if page.branding else {}
    (raw_dir / "branding.json").write_text(json.dumps(branding, indent=2))
    (raw_dir / "page.md").write_text((page.markdown or "")[:MAX_PAGE_CHARS])
    (raw_dir / "page.html").write_text((page.raw_html or "")[:MAX_PAGE_CHARS])
    saved = ["/raw/branding.json", "/raw/page.md", "/raw/page.html"]
    # Firecrawl hosts the screenshot for a limited time, so keep a copy.
    screenshot = await fetch_image(page.screenshot, http) if page.screenshot else None
    if screenshot:
        content, extension = screenshot
        (raw_dir / f"screenshot{extension}").write_bytes(content)
        saved.append(f"/raw/screenshot{extension}")

    images = await download_images(website_image_urls(page), brand_dir / "assets", http)
    logger.info(
        "Read %s: branding profile %s, %d characters of text, screenshot %s, %d images saved",
        url, "found" if branding else "missing", len(page.markdown or ""), "saved" if screenshot else "missing",
        len(images),
    )

    title = page.metadata.title if page.metadata else None
    lines = [
        f"Read {url}. Title: {title or 'unknown'}.",
        f"Saved: {', '.join(saved)}.",
        "Branding profile:",
        json.dumps(branding, indent=2) if branding else "(none found)",
        "First lines of text:",
        (page.markdown or "(no text found)")[:SUMMARY_TEXT_CHARS],
        "Images saved (file -> original URL):",
        *([f"- /assets/{name} -> {source}" for name, source in images] or ["(none)"]),
    ]
    return "\n".join(lines)


def without_inline_images(value):
    """A copy of `value` where every inline image (a 'data:' string) is replaced by a short note.

    Firecrawl often returns the logo as an inline SVG of 20,000+ characters, which
    the model cannot read and an email cannot use.
    """
    if isinstance(value, dict):
        return {key: without_inline_images(item) for key, item in value.items()}
    if isinstance(value, list):
        return [without_inline_images(item) for item in value]
    if isinstance(value, str) and value.startswith("data:"):
        return "(inline image left out)"
    return value


def website_image_urls(page) -> list[str]:
    """Image URLs of a Firecrawl page, logo first, without duplicates or inline data."""
    urls = []
    if page.branding:
        urls.append(page.branding.logo)
        urls.extend((page.branding.images or {}).values())
    urls.extend(page.images or [])
    return list(dict.fromkeys(url for url in urls if url and url.startswith(("http://", "https://"))))


async def fetch_image(url: str, http: httpx.AsyncClient) -> tuple[bytes, str] | None:
    """Download one image. Returns its bytes and file extension, or None if it is not a usable image."""
    try:
        response = await http.get(url)
    except httpx.HTTPError:
        return None
    content_type = response.headers.get("content-type", "").split(";")[0]
    extension = IMAGE_EXTENSIONS.get(content_type)
    if response.status_code != 200 or extension is None or len(response.content) > MAX_IMAGE_BYTES:
        return None
    return response.content, extension


async def download_images(urls: list[str], assets_dir: Path, http: httpx.AsyncClient) -> list[tuple[str, str]]:
    """Download up to MAX_IMAGES_TO_MODEL images into `assets_dir`. Returns (file name, original URL) pairs."""
    saved = []
    for url in urls:
        if len(saved) == MAX_IMAGES_TO_MODEL:
            break
        image = await fetch_image(url, http)
        if image is None:
            logger.debug("Image skipped (not a usable image): %s", url)
            continue
        content, extension = image
        name = f"image-{len(saved) + 1:02d}{extension}"
        (assets_dir / name).write_bytes(content)
        saved.append((name, url))
    return saved


def prepare_pdf(pdf_path: Path, raw_dir: Path, assets_dir: Path) -> PdfContent:
    """Save each page of a PDF as an image in `raw_dir`, and its large embedded images in `assets_dir`.

    Only the first MAX_PDF_PAGES pages are saved as images, to keep the model's input small.
    """
    stem = pdf_path.stem
    page_images, image_files = [], []
    seen = set()  # the same logo is often embedded on every page
    with pymupdf.open(pdf_path) as pdf:
        for number, page in enumerate(pdf, start=1):
            if number <= MAX_PDF_PAGES:
                name = f"{stem}-page-{number}.png"
                page.get_pixmap(dpi=PDF_PAGE_DPI).save(raw_dir / name)
                page_images.append(name)

            for image in page.get_images(full=True):
                xref = image[0]
                if xref in seen:
                    continue
                seen.add(xref)
                pixmap = pymupdf.Pixmap(pdf, xref)
                if pixmap.width < MIN_PDF_IMAGE_SIDE or pixmap.height < MIN_PDF_IMAGE_SIDE:
                    continue
                if pixmap.n - pixmap.alpha >= 4:  # CMYK cannot be saved as PNG
                    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
                name = f"{stem}-{len(image_files) + 1}.png"
                pixmap.save(assets_dir / name)
                image_files.append(name)
        page_count = pdf.page_count

    logger.info(
        "PDF %s: %d pages, %d turned into images, %d embedded images saved",
        pdf_path.name, page_count, len(page_images), len(image_files),
    )
    return PdfContent(page_count=page_count, page_images=page_images, image_files=image_files)
