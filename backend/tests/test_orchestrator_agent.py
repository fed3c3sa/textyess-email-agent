"""The orchestrator agent's plumbing, tested without a model: prompt, memory and streaming."""

import asyncio

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from app.config import Settings
from app.agentic_infra.agents.orchestrator.agent import (
    AGENT_NAME,
    answer_event,
    open_memory,
    orchestrator_prompt,
    stream_turn,
    user_message,
    with_asset_urls,
)
from app.agentic_infra.agents.orchestrator.tools import OrchestratorState
from app.schemas.design_system import Asset, DesignSystem, Identity
from app.schemas.email import Email, Section
from tests.conftest import make_pdf, png

SETTINGS = Settings(openrouter_api_key="test", firecrawl_api_key="test")


def test_local_asset_pointers_become_urls():
    design_system = DesignSystem(
        assets=[
            Asset(description="logo", role="logo", pointer="/assets/guide-1.png"),
            Asset(description="hero", role="hero", pointer="https://acme.com/hero.jpg"),
        ]
    )

    assets = with_asset_urls(design_system, "abcd1234", "http://localhost:8000").assets

    assert assets[0].pointer == "http://localhost:8000/brands/abcd1234/files/assets/guide-1.png"
    assert assets[1].pointer == "https://acme.com/hero.jpg"  # public URLs are kept


def test_prompt_shows_the_brand_and_the_email(store, brand_id):
    store.save(brand_id, DesignSystem(identity=Identity(name="Acme")))

    empty = orchestrator_prompt(store, SETTINGS, brand_id, Email())
    with_email = orchestrator_prompt(store, SETTINGS, brand_id, Email(sections=[Section(id="hero", reasoning="r", content="c")]))

    assert '"name": "Acme"' in empty
    assert "No email yet." in empty
    assert '"id": "hero"' in with_email


def test_memory_saves_and_reads_back_the_email(tmp_path):
    """Our Email type must survive the trip into the SQLite file and back."""
    section = Section(id="subject", reasoning="r", content="Hi")
    graph = StateGraph(OrchestratorState)
    graph.add_node("write", lambda state: {"email": {"write": section.model_dump(), "position": None}})
    graph.add_edge(START, "write")
    graph.add_edge("write", END)

    async def run():
        async with open_memory(tmp_path / "chat.sqlite") as memory:
            app = graph.compile(checkpointer=memory)
            config = {"configurable": {"thread_id": "t1"}}
            await app.ainvoke({"messages": []}, config)
            return (await app.aget_state(config)).values["email"]

    assert asyncio.run(run()) == Email(sections=[section])


class FakeRun:
    """Stands in for LangGraph's v3 run stream: fixed protocol events, then a fixed final state."""

    def __init__(self, events):
        self.events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, *error):
        pass

    async def __aiter__(self):
        for event in self.events:
            yield event

    async def output(self):
        return {"email": Email(sections=[Section(id="subject", reasoning="r", content="Hi")])}


class FakeAgent:
    def __init__(self, events):
        self.events = events

    async def astream_events(self, state, **options):
        return FakeRun(self.events)


def protocol(method: str, data) -> dict:
    return {"type": "event", "method": method, "params": {"namespace": [], "timestamp": 0, "data": data}}


def text(words: str) -> dict:
    return {"event": "content-block-delta", "index": 0, "delta": {"type": "text-delta", "text": words}}


def tool_call(name: str, args: dict) -> dict:
    return {"event": "content-block-finish", "index": 0, "content": {"type": "tool_call", "id": "c1", "name": name, "args": args}}


def test_stream_turn_passes_tool_events_and_only_the_orchestrators_words():
    agent = FakeAgent(
        [
            protocol("custom", {"type": "status", "text": "Reading the website..."}),
            protocol("messages", (text("scraper thinking"), {"lc_agent_name": "scraper"})),  # inside learn_brand
            protocol("messages", ({"event": "message-finish", "metadata": {"cost": 0.002}}, {"lc_agent_name": "scraper"})),
            protocol("messages", (text("Done."), {"lc_agent_name": AGENT_NAME})),
            protocol("messages", ({"event": "message-finish", "metadata": {"cost": 0.001}}, {"lc_agent_name": AGENT_NAME})),
        ]
    )

    async def run():
        return [event async for event in stream_turn(agent, "s1", "b1", HumanMessage("Hello"))]

    events = asyncio.run(run())

    assert [e["type"] for e in events] == ["status", "message", "email_replaced", "done"]
    assert events[1]["text"] == "Done."
    assert events[2]["email"]["sections"][0]["id"] == "subject"
    assert events[3]["cost_usd"] == 0.003  # both model calls are paid for


def test_a_finished_write_section_call_is_drafted_at_once():
    hero = {"section_id": "hero", "reasoning": "Big promise.", "content": "<h1>-20%</h1>"}

    assert answer_event(tool_call("write_section", hero))["section"]["id"] == "hero"
    assert answer_event(tool_call("remove_section", {"section_id": "old"})) is None
    assert answer_event(tool_call("write_section", {"section_id": "cta"})) is None  # incomplete: the tool explains
    assert answer_event(text("Hi"))["text"] == "Hi"


def test_a_refused_section_is_never_drafted():
    merged = {"section_id": "subject_preheader", "reasoning": "r", "content": "Subject: Hi"}
    assert answer_event(tool_call("write_section", merged)) is None


def test_a_plain_message_is_just_text(store, brand_id):
    assert user_message(store, SETTINGS, brand_id, "Hello").content == "Hello"
    assert user_message(store, SETTINGS, brand_id, "Shorter", "hero").content.startswith("<selected_section>hero</selected_section>")


def test_an_attached_image_is_shown_to_the_model_with_its_url(store, brand_id, brand_dir):
    (brand_dir / "uploads" / "shoe.png").write_bytes(png(10, 10))

    message = user_message(store, SETTINGS, brand_id, "Use this in the hero", files=["shoe.png"])

    assert f"http://localhost:8000/brands/{brand_id}/files/uploads/shoe.png" in message.content[0]["text"]
    assert [block["type"] for block in message.content] == ["text", "text", "image"]


def test_an_attached_pdf_shows_its_pages_and_lists_its_images(store, brand_id, brand_dir):
    make_pdf(brand_dir / "uploads" / "promo.pdf", pages=2)

    message = user_message(store, SETTINGS, brand_id, "Follow this brief", files=["promo.pdf"])

    assert "/files/assets/promo-1.png" in message.content[0]["text"]  # the logo inside the PDF
    assert sum(block["type"] == "image" for block in message.content) == 2  # one per page

