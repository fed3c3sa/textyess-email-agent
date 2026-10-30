"""The orchestrator agent, its memory, and one chat turn streamed as events.

`build_orchestrator` creates the agent once: the model, the tools, the memory
(checkpointer), and a prompt rebuilt before every model call, so it always shows
the latest design system and the current email. `stream_turn` runs one user message
and yields the events the UI needs: chat text, sections and progress while the agent
works, then the final email, the cost and the time of the turn.
"""

import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.stream import CustomTransformer
from pydantic import ValidationError

from app.config import Settings
from app.agentic_infra.agents.scraper.sources import prepare_pdf
from app.agentic_infra.shared.images import IMAGE_SUFFIXES, labelled_image_blocks
from app.agentic_infra.agents.orchestrator.tools import (
    OrchestratorContext,
    OrchestratorState,
    build_orchestrator_tools,
    mixes_subject_and_preheader,
)
from app.agentic_infra.shared.model import build_model
from app.agentic_infra.prompts import render_system_prompt
from app.schemas.design_system import DesignSystem
from app.schemas.email import Email, Section
from app.schemas.events import DoneEvent, EmailReplacedEvent, ErrorEvent, MessageEvent, SectionDraftEvent
from app.storage.brands import BrandStore

logger = logging.getLogger(__name__)

AGENT_NAME = "orchestrator"
STATE_TYPES = [("app.schemas.email", "Email"), ("app.schemas.email", "Section")]  # our types inside the state


@asynccontextmanager
async def open_memory(path: Path) -> AsyncGenerator[AsyncSqliteSaver]:
    """The checkpointer: every session's messages and email, in one SQLite file.

    Our types are registered, so the checkpointer may read them back from the file.
    """
    async with aiosqlite.connect(path) as connection:
        yield AsyncSqliteSaver(connection, serde=JsonPlusSerializer(allowed_msgpack_modules=STATE_TYPES))


def build_orchestrator(store: BrandStore, settings: Settings, memory: AsyncSqliteSaver):
    """The orchestrator agent. `memory` keeps each session's messages and email."""

    @dynamic_prompt
    def prompt(request: ModelRequest) -> str:
        brand_id = request.runtime.context.brand_id
        return orchestrator_prompt(store, settings, brand_id, request.state.get("email") or Email())

    return create_agent(
        model=build_model(settings, settings.orchestrator_model),
        tools=build_orchestrator_tools(store, settings),
        middleware=[prompt],
        state_schema=OrchestratorState,
        context_schema=OrchestratorContext,
        checkpointer=memory,
        name=AGENT_NAME,
    )


def orchestrator_prompt(store: BrandStore, settings: Settings, brand_id: str, email: Email) -> str:
    """The system prompt with the brand's latest design system and the current email."""
    design_system = with_asset_urls(store.load(brand_id) or DesignSystem(), brand_id, settings.public_url)
    return render_system_prompt(
        "orchestrator_system",
        design_system=design_system.model_dump_json(indent=2),
        current_email=email.model_dump_json(indent=2) if email.sections else "No email yet.",
    ).content


def with_asset_urls(design_system: DesignSystem, brand_id: str, public_url: str) -> DesignSystem:
    """The design system with local asset pointers ('/assets/logo.png') turned into URLs served by the API."""
    assets = [
        asset.model_copy(update={"pointer": f"{public_url}/brands/{brand_id}/files{asset.pointer}"})
        if asset.pointer.startswith("/")
        else asset
        for asset in design_system.assets
    ]
    return design_system.model_copy(update={"assets": assets})


def user_message(
    store: BrandStore,
    settings: Settings,
    brand_id: str,
    text: str,
    selected_section: str | None = None,
    files: list[str] = (),
) -> HumanMessage:
    """The user's chat message for the model: the text, the selected section, and the attached files.

    `files` are names in the brand's uploads/. Images and the pages of PDFs are attached as
    images, so the model sees them. Each usable image is listed with its URL, so the model
    can put it in the email.
    """
    if selected_section:
        text = f"<selected_section>{selected_section}</selected_section>\n{text}"
    if not files:
        return HumanMessage(text)

    brand_dir = store.brand_dir(brand_id)
    files_url = f"{settings.public_url}/brands/{brand_id}/files"
    lines = [text, "", "Files the user attached to this message:"]
    images = []  # what the model will see
    for name in files:
        path = brand_dir / "uploads" / Path(name).name
        if path.suffix.lower() == ".pdf":
            pdf = prepare_pdf(path, brand_dir / "raw", brand_dir / "assets")
            images += [brand_dir / "raw" / page for page in pdf.page_images]
            lines.append(f"- {path.name}: a PDF, its pages are shown below.")
            lines += [f"  - image found inside it, usable in the email: {files_url}/assets/{f}" for f in pdf.image_files]
        elif path.suffix.lower() in IMAGE_SUFFIXES:
            images.append(path)
            lines.append(f"- {path.name}: shown below, usable in the email: {files_url}/uploads/{path.name}")

    blocks = labelled_image_blocks([(image.name, image) for image in images])
    return HumanMessage(content=[{"type": "text", "text": "\n".join(lines)}, *blocks])


async def stream_turn(agent, session_id: str, brand_id: str, message: HumanMessage) -> AsyncIterator[dict]:
    """Run one user message (see user_message) and yield its events as dicts.

    Uses LangGraph's v3 event streaming (experimental): one ordered log of protocol events,
    with the model's answers split into content blocks.
    While the agent works: 'message' (chat text), 'status' and section events.
    At the end: 'email_replaced' with the final email, so the preview is always
    right even after parallel tool calls, then 'done'. On failure: 'error'.
    """
    config = {"configurable": {"thread_id": session_id}}
    start, cost = time.time(), 0.0
    logger.info("Turn started: session %s, brand %s, message of %d characters", session_id, brand_id, len(message.text))
    try:
        run = await agent.astream_events(
            {"messages": [message]},
            config=config,
            context=OrchestratorContext(brand_id=brand_id),
            version="v3",
            transformers=[CustomTransformer],  # the events our tools send
        )
        async with run:
            async for event in run:
                data = event["params"]["data"]
                if event["method"] == "custom":  # events sent by the tools: sections and progress
                    yield data
                    continue
                if event["method"] != "messages":
                    continue
                block, metadata = data
                if block["event"] == "message-finish":  # every model call, the scraper's included
                    cost += block.get("metadata", {}).get("cost", 0)
                if metadata.get("lc_agent_name") == AGENT_NAME and (ui_event := answer_event(block)):
                    yield ui_event  # not the scraper's words, inside learn_brand
            state = await run.output()
        yield EmailReplacedEvent(email=state.get("email") or Email()).model_dump()
    except Exception as error:
        logger.exception("Turn failed: session %s", session_id)
        yield ErrorEvent(message=str(error)).model_dump()
        return
    logger.info("Turn done: session %s in %.1f s for $%.4f", session_id, time.time() - start, cost)
    yield DoneEvent(cost_usd=round(cost, 6), seconds=round(time.time() - start, 1)).model_dump()


def answer_event(block: dict) -> dict | None:
    """The UI event for one content block of the orchestrator's answer, if it has one.

    Chat text streams as it comes. A write_section call becomes a section draft as soon as
    the model finishes writing it, before the tool runs, so the preview streams part by part
    even when the model writes several sections in one answer.
    """
    if block["event"] == "content-block-delta" and block["delta"]["type"] == "text-delta":
        return MessageEvent(text=block["delta"]["text"]).model_dump()
    call = block.get("content") or {}
    if block["event"] != "content-block-finish" or call.get("type") != "tool_call" or call["name"] != "write_section":
        return None
    args = call["args"]
    try:
        section = Section(id=args["section_id"], reasoning=args["reasoning"], content=args["content"])
    except (KeyError, ValidationError):
        return None  # the tool refuses it and explains why
    if mixes_subject_and_preheader(section.id):  # the tool refuses it, so it never shows
        return None
    return SectionDraftEvent(section=section).model_dump()

