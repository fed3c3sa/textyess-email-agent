"""Learn a brand: gather its sources, run the scraper agent once, save the design system.

The steps run in order:
1. Read the website with Firecrawl, if there is a URL.
2. Save the pages of every uploaded PDF as images, and the images inside them as assets.
3. Build one user message with all the text and every image. The images go there,
   and not through a tool, because the model can only see images in a user message.
4. Run the agent. It can search the saved text files, and returns a ScrapeResult.
5. Save the design system (BrandStore keeps the user's notes) and return the result.
"""

import base64
from collections.abc import Callable
from pathlib import Path

import httpx
import pymupdf
from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from firecrawl import AsyncFirecrawl
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage
from langchain_openrouter import ChatOpenRouter

from app.config import Settings
from app.prompts import render_system_prompt, render_text
from app.schemas.design_system import DesignSystem, ScrapeResult
from app.scraper.sources import prepare_pdf, read_website
from app.storage.brands import BrandStore

READ_ONLY_FILE_TOOLS = ["ls", "read_file", "glob", "grep"]
IMAGE_FOLDERS = ("raw", "uploads", "assets")  # the order the images appear in the message
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}  # SVG is left out: models cannot see it
MAX_IMAGE_WIDTH = 1024  # wider images are shrunk, to keep the request small


async def scrape_brand(
    store: BrandStore,
    brand_id: str,
    url: str | None,
    settings: Settings,
    report: Callable[[str], None] = lambda text: None,
) -> ScrapeResult:
    """Learn a brand from its website and uploaded files, save the design system and return it.

    `report` receives short progress texts, which the callers show to the user.
    Raises if the model does not return a valid design system.
    """
    brand_dir = store.brand_dir(brand_id)

    website_summary = "No website was given."
    if url:
        report("Reading the website...")
        firecrawl = AsyncFirecrawl(api_key=settings.firecrawl_api_key)
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
            website_summary = await read_website(url, brand_dir, firecrawl, http)

    report("Reading the documents...")
    for pdf_path in sorted((brand_dir / "uploads").glob("*.pdf")):
        prepare_pdf(pdf_path, brand_dir / "raw", brand_dir / "assets")

    report("Building the design system...")
    message = build_first_message(brand_dir, url, website_summary, store.load(brand_id))
    agent = create_agent(
        model=ChatOpenRouter(model=settings.model, openrouter_api_key=settings.openrouter_api_key),
        system_prompt=render_system_prompt("scraper_system"),
        middleware=[
            FilesystemMiddleware(
                backend=FilesystemBackend(root_dir=brand_dir, virtual_mode=True),
                tools=READ_ONLY_FILE_TOOLS,
            )
        ],
        response_format=ToolStrategy(ScrapeResult),
    )
    output = await agent.ainvoke({"messages": [message]}, config={"recursion_limit": settings.scraper_max_steps})

    result: ScrapeResult = output["structured_response"]
    if url:
        result.design_system.identity.source_url = url
    store.save(brand_id, result.design_system)
    return result


def build_first_message(
    brand_dir: Path, url: str | None, website_summary: str, current: DesignSystem | None
) -> HumanMessage:
    """The scraper's input: the text of prompts/scraper_user.md, then every image, each after its path."""
    uploads = sorted(path.name for path in (brand_dir / "uploads").iterdir())
    text = render_text(
        "scraper_user",
        website=url or "None.",
        website_summary=website_summary,
        uploads="\n".join(f"- /uploads/{name}" for name in uploads) or "None.",
        current_design_system=current.model_dump_json(indent=2) if current else "Nothing yet.",
    )

    content = [{"type": "text", "text": text}]
    for folder in IMAGE_FOLDERS:
        for path in sorted((brand_dir / folder).iterdir()):
            if path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            block = image_block(path)
            if block:
                content.append({"type": "text", "text": f"/{folder}/{path.name}:"})
                content.append(block)
    return HumanMessage(content=content)


def image_block(path: Path) -> dict | None:
    """The image as a PNG content block, at most MAX_IMAGE_WIDTH wide. None if it cannot be read."""
    try:
        pixmap = pymupdf.Pixmap(path)
    except Exception:
        return None
    while pixmap.width > MAX_IMAGE_WIDTH:
        pixmap.shrink(1)  # halves the width and the height
    if pixmap.n - pixmap.alpha >= 4:  # CMYK cannot be saved as PNG
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
    data = base64.b64encode(pixmap.tobytes("png")).decode()
    return {"type": "image", "base64": data, "mime_type": "image/png"}
