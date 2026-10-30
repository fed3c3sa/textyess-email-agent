"""The orchestrator's tools and the email renderer, tested without a model.

A tool's `.func` is the plain function behind it. A SimpleNamespace stands in for
the runtime LangChain would pass: the state, the context, the tool call id, and a
stream writer that collects the events.
"""

from types import SimpleNamespace

import pytest
from langgraph.graph import END, START, StateGraph

from app.config import Settings
from app.render import render_email
from app.agentic_infra.agents.orchestrator.tools import (
    OrchestratorContext,
    OrchestratorState,
    apply_email_edit,
    build_orchestrator_tools,
    drop_section,
    put_section,
)
from app.schemas.design_system import DesignSystem
from app.schemas.email import Email, Section


def section(section_id: str, content: str = "x") -> Section:
    return Section(id=section_id, reasoning="because", content=content)


EMAIL = Email(sections=[section("subject"), section("hero"), section("footer")])


def ids(email: Email) -> list[str]:
    return [s.id for s in email.sections]


def test_a_new_section_goes_at_the_end():
    email, index = put_section(EMAIL, section("cta"), None)
    assert ids(email) == ["subject", "hero", "footer", "cta"]
    assert index == 3


def test_a_replaced_section_stays_where_it_was():
    email, index = put_section(EMAIL, section("hero", "new"), None)
    assert ids(email) == ["subject", "hero", "footer"]
    assert (index, email.sections[1].content) == (1, "new")


def test_a_position_moves_the_section():
    email, index = put_section(EMAIL, section("footer"), 1)
    assert ids(email) == ["subject", "footer", "hero"]
    assert index == 1


def test_drop_section_ignores_an_unknown_id():
    assert ids(drop_section(EMAIL, "cta")) == ["subject", "hero", "footer"]


def test_edits_from_tools_called_at_the_same_time_are_all_kept():
    """The bug of the first real run: the model called write_section several times at once."""
    graph = StateGraph(OrchestratorState)
    graph.add_node("hero", lambda state: {"email": {"write": section("hero").model_dump(), "position": None}})
    graph.add_node("footer", lambda state: {"email": {"write": section("footer").model_dump(), "position": None}})
    graph.add_edge(START, "hero")
    graph.add_edge(START, "footer")
    graph.add_edge("hero", END)
    graph.add_edge("footer", END)

    state = graph.compile().invoke({"messages": []})

    assert sorted(ids(state["email"])) == ["footer", "hero"]


@pytest.fixture
def tools(store, brand_id):
    settings = Settings(openrouter_api_key="test", firecrawl_api_key="test")
    return {t.name: t for t in build_orchestrator_tools(store, settings)}


def fake_runtime(brand_id: str, email: Email | None = None, events: list | None = None) -> SimpleNamespace:
    state = {"email": email} if email else {}
    writer = events.append if events is not None else (lambda event: None)
    return SimpleNamespace(
        state=state, context=OrchestratorContext(brand_id=brand_id), tool_call_id="call-1", stream_writer=writer
    )


def test_write_section_updates_the_state_and_sends_an_event(tools, brand_id):
    events = []
    runtime = fake_runtime(brand_id, EMAIL, events)

    command = tools["write_section"].func(section_id="hero", reasoning="r", content="<h1>New</h1>", runtime=runtime)

    assert apply_email_edit(EMAIL, command.update["email"]).sections[1].content == "<h1>New</h1>"
    assert events[0]["type"] == "section_updated"
    assert events[0]["index"] == 1


def test_write_section_starts_an_email_from_nothing(tools, brand_id):
    events = []
    command = tools["write_section"].func(
        section_id="subject", reasoning="r", content="Black Friday", runtime=fake_runtime(brand_id, events=events)
    )
    assert ids(apply_email_edit(Email(), command.update["email"])) == ["subject"]
    assert events[0]["type"] == "section_added"


def test_write_section_refuses_subject_and_preheader_in_one_part(tools, brand_id):
    """The bug of a real run: 'subject_preheader' left the email with no subject."""
    events = []
    answer = tools["write_section"].func(
        section_id="subject_preheader", reasoning="r", content="Subject: Hi", runtime=fake_runtime(brand_id, EMAIL, events)
    )
    assert "'subject' and 'preheader'" in answer
    assert events == []


def test_remove_section_explains_an_unknown_id(tools, brand_id):
    answer = tools["remove_section"].func(section_id="cta", runtime=fake_runtime(brand_id, EMAIL))
    assert answer == "There is no section 'cta'. Sections: subject, hero, footer."


def test_update_design_system_changes_the_brand_but_not_the_notes(tools, store, brand_id):
    store.save(brand_id, DesignSystem())
    update = tools["update_design_system"].func

    assert update(field="identity.language", value="it", runtime=fake_runtime(brand_id)) == "Changed identity.language."
    assert store.load(brand_id).identity.language == "it"
    assert "save_note" in update(field="user_notes", value=[], runtime=fake_runtime(brand_id))
    assert "Could not change" in update(field="nope", value=1, runtime=fake_runtime(brand_id))


def test_save_note_saves_it_for_the_brand(tools, store, brand_id):
    tools["save_note"].func(note="No emojis.", runtime=fake_runtime(brand_id))
    assert store.load(brand_id).user_notes == ["No emojis."]


def test_render_puts_subject_and_preheader_in_their_place():
    email = Email(
        sections=[
            section("subject", "Sale & more"),
            section("preheader", "Ends tonight"),
            section("hero", "<h1>-20%</h1>"),
            section("footer", "<p>Bye</p>"),
        ]
    )

    page = render_email(email)

    assert "<title>Sale &amp; more</title>" in page
    assert ">Ends tonight</div>" in page
    assert page.index("<h1>-20%</h1>") < page.index("<p>Bye</p>")
    assert page.count("Sale &amp; more") == 1  # the subject is not repeated in the body
    assert '<td align="center">' in page  # the sections sit in a centered column
    assert page.index('max-width:600px') < page.index("<h1>-20%</h1>")
