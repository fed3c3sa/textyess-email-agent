"""The orchestrator agent, its memory, and one chat turn streamed as events.

`build_orchestrator` creates the agent once: the model, the tools, the memory
(checkpointer), and a prompt rebuilt before every model call, so it always shows
the latest design system and the current email. `stream_turn` runs one user message
and yields the events the UI needs: chat text, sections and progress while the agent
works, then the final email, the cost and the time of the turn.
"""

import json
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, dynamic_prompt
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.config import Settings
from app.agentic_infra.agents.orchestrator.tools import OrchestratorContext, OrchestratorState, build_orchestrator_tools
from app.agentic_infra.model import build_model
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
        model=build_model(settings),
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


async def stream_turn(
    agent, session_id: str, brand_id: str, text: str, selected_section: str | None = None
) -> AsyncIterator[dict]:
    """Run one user message and yield its events as dicts.

    While the agent works: 'message' (chat text), 'status' and section events.
    At the end: 'email_replaced' with the final email, so the preview is always
    right even after parallel tool calls, then 'done'. On failure: 'error'.
    """
    if selected_section:
        text = f"<selected_section>{selected_section}</selected_section>\n{text}"
    config = {"configurable": {"thread_id": session_id}}
    start, cost = time.time(), 0.0
    drafts: dict = {}  # the tool calls the model is writing, see drafted_sections
    logger.info(
        "Turn started: session %s, brand %s, message of %d characters%s",
        session_id, brand_id, len(text), f", about section {selected_section!r}" if selected_section else "",
    )
    try:
        async for chunk in agent.astream(
            {"messages": [HumanMessage(text)]},
            config=config,
            context=OrchestratorContext(brand_id=brand_id),
            stream_mode=["messages", "custom"],
            version="v2",
        ):
            if chunk["type"] == "custom":  # events sent by the tools: sections and progress
                yield chunk["data"]
                continue
            token, metadata = chunk["data"]
            if not isinstance(token, AIMessageChunk):
                continue
            cost += token.response_metadata.get("cost", 0)  # every model call, the scraper's included
            if metadata.get("lc_agent_name") != AGENT_NAME:  # the scraper, inside learn_brand
                continue
            if token.text:
                yield MessageEvent(text=token.text).model_dump()
            for section in drafted_sections(token, drafts):
                yield SectionDraftEvent(section=section).model_dump()

        state = await agent.aget_state(config)
        yield EmailReplacedEvent(email=state.values.get("email") or Email()).model_dump()
    except Exception as error:
        logger.exception("Turn failed: session %s", session_id)
        yield ErrorEvent(message=str(error)).model_dump()
        return
    logger.info("Turn done: session %s in %.1f s for $%.4f", session_id, time.time() - start, cost)
    yield DoneEvent(cost_usd=round(cost, 6), seconds=round(time.time() - start, 1)).model_dump()


def drafted_sections(token: AIMessageChunk, drafts: dict) -> list[Section]:
    """The sections whose write_section call the model has just finished writing, before the tool runs.

    The arguments of each tool call arrive in pieces. `drafts` collects them per call; once
    a call's pieces form valid JSON, the call is complete and its section is returned, once.
    This keeps the preview streaming part by part even when the model writes several
    sections in one answer.
    """
    finished = []
    for piece in token.tool_call_chunks:
        call = drafts.setdefault((token.id, piece["index"]), {"name": "", "args": "", "sent": False})
        call["name"] += piece.get("name") or ""
        call["args"] += piece.get("args") or ""
        if call["name"] != "write_section" or call["sent"]:
            continue
        try:
            arguments = json.loads(call["args"])
            section = Section(id=arguments["section_id"], reasoning=arguments["reasoning"], content=arguments["content"])
        except (json.JSONDecodeError, KeyError, TypeError):
            continue  # not complete yet
        call["sent"] = True
        finished.append(section)
    return finished

