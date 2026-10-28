import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.email import Email, Section
from app.schemas.events import SectionAddedEvent, StreamEvent

hero = Section(id="hero", kind="hero", reasoning="Big promise first.", content="<h1>-20%</h1>")


def test_reasoning_comes_before_content():
    """The model writes fields in order, so the reason must be streamed first."""
    fields = list(Section.model_fields)
    assert fields.index("reasoning") < fields.index("content")


def test_section_kind_is_restricted():
    with pytest.raises(ValidationError):
        Section(id="x", kind="banner", reasoning="r", content="c")


def test_empty_email_is_valid():
    assert Email().sections == []


def test_event_round_trip_picks_the_right_class():
    """A JSON payload is routed to the right event class by its `type`."""
    adapter = TypeAdapter(StreamEvent)
    sent = SectionAddedEvent(section=hero, index=0)
    received = adapter.validate_json(sent.model_dump_json())
    assert isinstance(received, SectionAddedEvent)
    assert received == sent


def test_unknown_event_type_is_rejected():
    with pytest.raises(ValidationError):
        TypeAdapter(StreamEvent).validate_python({"type": "nope"})
