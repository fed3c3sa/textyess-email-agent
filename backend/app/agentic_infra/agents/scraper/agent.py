"""Learn a brand: gather its sources, run the scraper agent once, save the design system.

The steps run in order:
1. Read the website with Firecrawl, if there is a URL.
2. Save the pages of every uploaded PDF as images, and the images inside them as assets.
3. Build one user message with all the text and every image. The images go there,
   and not through a tool, because the model can only see images in a user message.
4. Run the agent. It searches the saved text files, within a limit of model calls.
5. One last call asks for the ScrapeResult, as a JSON schema. No tool is forced, so it
   works with every model, Claude included (it refuses a forced tool choice).
6. Save the design system (BrandStore keeps the user's notes) and return the result.
"""

import logging
from collections.abc import Callable
from pathlib import Path

import httpx
from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from firecrawl import AsyncFirecrawl
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage

from app.config import SCRAPER_MAX_MODEL_CALLS, Settings
from app.agentic_infra.images import labelled_image_blocks
from app.agentic_infra.model import build_model
from app.agentic_infra.prompts import render_system_prompt, render_text
from app.schemas.design_system import DesignSystem, ScrapeResult
from app.agentic_infra.agents.scraper.sources import prepare_pdf, read_website
from app.storage.brands import BrandStore

logger = logging.getLogger(__name__)

READ_ONLY_FILE_TOOLS = ["ls", "read_file", "glob", "grep"]
IMAGE_FOLDERS = ("raw", "uploads", "assets")  # the order the images appear in the message


async def scrape_brand(
    store: BrandStore,
    brand_id: str,
    url: str | None,
    settings: Settings,
    report: Callable[[str], None] = lambda text: None,
    callbacks: list[BaseCallbackHandler] | None = None,
) -> ScrapeResult:
    """Learn a brand from its website and uploaded files, save the design system and return it.

    `report` receives short progress texts, which the callers show to the user.
    `callbacks` are LangChain callbacks for every model call, e.g. a CostCounter.
    Raises if the model does not return a valid design system.
    """
    brand_dir = store.brand_dir(brand_id)
    logger.info("Learning brand %s from %s", brand_id, url or "the uploaded files only")

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
    logger.info("Scraper starts with %d images in its first message", sum(b["type"] == "image" for b in message.content))
    model = build_model(settings)
    system_prompt = render_system_prompt("scraper_system")
    agent = create_agent(
        model=model,
        system_prompt=system_prompt,
        middleware=[
            FilesystemMiddleware(
                backend=FilesystemBackend(root_dir=brand_dir, virtual_mode=True),
                tools=READ_ONLY_FILE_TOOLS,
            ),
            ModelCallLimitMiddleware(run_limit=SCRAPER_MAX_MODEL_CALLS),  # stops the search loop
        ],
        name="scraper",
    )
    config = {"callbacks": callbacks} if callbacks else None  # e.g. a CostCounter
    output = await agent.ainvoke({"messages": [message]}, config=config)

    logger.info("Scraper finished searching after %d messages", len(output["messages"]))

    report("Writing the design system...")
    finish = HumanMessage(render_text("scraper_finish"))
    messages = [system_prompt, *output["messages"], finish]
    result = await model.with_structured_output(ScrapeResult, method="json_schema").ainvoke(messages, config=config)
    if result is None:
        raise RuntimeError("The scraper ended without a design system.")
    if url:
        result.design_system.identity.source_url = url
    store.save(brand_id, result.design_system)
    logger.info("Brand %s learned, %d conflicts between website and documents", brand_id, len(result.conflicts))
    return result


def build_first_message(
    brand_dir: Path, url: str | None, website_summary: str, current: DesignSystem | None
) -> HumanMessage:
    """The scraper's input: the text of prompts/scraper_user.md, then up to MAX_IMAGES_TO_MODEL images, each after its path."""
    uploads = sorted(path.name for path in (brand_dir / "uploads").iterdir())
    text = render_text(
        "scraper_user",
        website=url or "None.",
        website_summary=website_summary,
        uploads="\n".join(f"- /uploads/{name}" for name in uploads) or "None.",
        current_design_system=current.model_dump_json(indent=2) if current else "Nothing yet.",
    )

    images = [
        (f"/{folder}/{path.name}", path)  # labelled with the path the file tools use
        for folder in IMAGE_FOLDERS
        for path in sorted((brand_dir / folder).iterdir())
    ]
    return HumanMessage(content=[{"type": "text", "text": text}, *labelled_image_blocks(images)])
