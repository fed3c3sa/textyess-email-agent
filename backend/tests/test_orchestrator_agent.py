"""The orchestrator agent's plumbing, tested without a model: prompt, memory and streaming."""

import asyncio
from types import SimpleNamespace

from langchain_core.messages import AIMessageChunk
from langgraph.graph import END, START, StateGraph

from app.config import Settings
from app.agentic_infra.agents.orchestrator.agent import AGENT_NAME, open_memory, orchestrator_prompt, stream_turn, with_asset_urls
from app.agentic_infra.agents.orchestrator.tools import OrchestratorState
from app.schemas.design_system import Asset, DesignSystem, Identity
from app.schemas.email import Email, Section

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


class FakeAgent:
    """Streams fixed chunks, then gives a fixed final state."""

    def __init__(self, chunks):
        self.chunks = chunks

    async def astream(self, state, **options):
        for chunk in self.chunks:
            yield chunk

    async def aget_state(self, config):
        return SimpleNamespace(values={"email": Email(sections=[Section(id="subject", reasoning="r", content="Hi")])})


def token(text: str, agent: str, cost: float = 0) -> dict:
    message = AIMessageChunk(content=text, response_metadata={"cost": cost} if cost else {})
    return {"type": "messages", "data": (message, {"lc_agent_name": agent})}


def test_stream_turn_passes_tool_events_and_only_the_orchestrators_words():
    agent = FakeAgent(
        [
            {"type": "custom", "data": {"type": "status", "text": "Reading the website..."}},
            token("scraper thinking", "scraper", cost=0.002),  # the scraper, inside learn_brand
            token("Done.", AGENT_NAME, cost=0.001),
        ]
    )

    async def run():
        return [event async for event in stream_turn(agent, "s1", "b1", "Hello")]

    events = asyncio.run(run())

    assert [e["type"] for e in events] == ["status", "message", "email_replaced", "done"]
    assert events[1]["text"] == "Done."
    assert events[2]["email"]["sections"][0]["id"] == "subject"
    assert events[3]["cost_usd"] == 0.003  # both model calls are paid for
