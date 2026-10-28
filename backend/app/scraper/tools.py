"""What the scraper gets from a website and from a PDF.

`scrape_website` is the scraper's only tool: it asks Firecrawl for the page's
branding, text, HTML, images and screenshot, so no browser runs locally. It writes
everything into the brand folder (`raw/`, `assets/`) and returns a short summary, so
the agent's context stays small. If the site can't be read, it returns an error
message instead of raising, so the agent can continue with the other sources.

`prepare_pdf` is not a tool. It runs before the scraper: it saves each page as an
image, which goes to the model in its first message, and saves the images found
inside the PDF (logos, photos) as assets.

Paths in the summaries start with `/`, because the agent's file tools see the
brand folder as their root.
"""

import json
from pathlib import Path

import httpx
import pymupdf
from firecrawl import AsyncFirecrawl
from langchain_core.tools import BaseTool, tool

from app.schemas.pdf import PdfContent

FIRECRAWL_FORMATS = ["branding", "markdown", "rawHtml", "images", "screenshot"]
MAX_IMAGES = 15
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
TEXT_PREVIEW_CHARS = 1500
MAX_PDF_PAGES = 10
PDF_PAGE_DPI = 110  # enough to read small text on a page
MIN_PDF_IMAGE_SIDE = 100


def build_scraper_tools(brand_dir: Path, firecrawl: AsyncFirecrawl, http: httpx.AsyncClient) -> list[BaseTool]:
    """The scraper's tools, bound to one brand folder, one Firecrawl client and one HTTP client."""
    raw_dir = brand_dir / "raw"
    assets_dir = brand_dir / "assets"

    @tool(parse_docstring=True)
    async def scrape_website(url: str) -> str:
        """Read a website and save what is needed to describe the brand.

        Saves into the brand folder: /raw/branding.json (colors, fonts, typography,
        button styles, logo and tone, measured on the live page), /raw/page.md (the
        visible text, for the brand's voice), /raw/page.html (the HTML, for header,
        hero and footer snippets), /raw/screenshot (an image of the page), and
        up to 15 images in /assets (logo first), downloaded so you can look at them.
        Returns the branding profile, the first lines of text, and the images saved
        with their original URL. Use the original URL as an asset's pointer.

        Args:
            url: Full address of the website, starting with http:// or https://.
        """
        try:
            page = await firecrawl.scrape(url, formats=FIRECRAWL_FORMATS, only_main_content=False)
        except Exception as error:
            return f"Could not read {url}: {error}"

        branding = page.branding.model_dump(exclude_none=True) if page.branding else {}
        (raw_dir / "branding.json").write_text(json.dumps(branding, indent=2))
        (raw_dir / "page.md").write_text(page.markdown or "")
        (raw_dir / "page.html").write_text(page.raw_html or "")
        saved = ["/raw/branding.json", "/raw/page.md", "/raw/page.html"]
        # Firecrawl hosts the screenshot for a limited time, so keep a copy.
        screenshot = await fetch_image(page.screenshot, http) if page.screenshot else None
        if screenshot:
            content, extension = screenshot
            (raw_dir / f"screenshot{extension}").write_bytes(content)
            saved.append(f"/raw/screenshot{extension}")

        images = await download_images(website_image_urls(page), assets_dir, http)

        title = page.metadata.title if page.metadata else None
        lines = [
            f"Read {url}. Title: {title or 'unknown'}.",
            f"Saved: {', '.join(saved)}.",
            "Branding profile:",
            json.dumps(branding, indent=2) if branding else "(none found)",
            "First lines of text:",
            (page.markdown or "(no text found)")[:TEXT_PREVIEW_CHARS],
            "Images saved (file -> original URL):",
            *([f"- /assets/{name} -> {source}" for name, source in images] or ["(none)"]),
        ]
        return "\n".join(lines)

    return [scrape_website]


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
    """Download up to MAX_IMAGES images into `assets_dir`. Returns (file name, original URL) pairs."""
    saved = []
    for url in urls:
        if len(saved) == MAX_IMAGES:
            break
        image = await fetch_image(url, http)
        if image is None:
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

    return PdfContent(page_count=page_count, page_images=page_images, image_files=image_files)
