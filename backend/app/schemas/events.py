"""The SSE event contract between the backend and the UI.

Every event has a `type`. `StreamEvent` is a discriminated union on that field,
so the frontend can switch on `type` and every payload is validated.
"""

from typing import Annotated, Literal

from fastapi.sse import ServerSentEvent
from pydantic import BaseModel, Field

from app.schemas.design_system import Conflict, DesignSystem
from app.schemas.email import Email, Section


class StatusEvent(BaseModel):
    """Progress text, e.g. 'Scraping the website...'."""

    type: Literal["status"] = "status"
    text: str


class MessageEvent(BaseModel):
    """A chunk of the agent's chat reply."""

    type: Literal["message"] = "message"
    text: str


class SectionAddedEvent(BaseModel):
    """A new section was added to the email."""

    type: Literal["section_added"] = "section_added"
    section: Section
    index: int = Field(description="Position of the section in the email.")


class SectionUpdatedEvent(BaseModel):
    """An existing section was changed, and maybe moved. It keeps its id."""

    type: Literal["section_updated"] = "section_updated"
    section: Section
    index: int = Field(description="Position of the section in the email.")


class SectionRemovedEvent(BaseModel):
    """A section was removed from the email."""

    type: Literal["section_removed"] = "section_removed"
    section_id: str


class EmailReplacedEvent(BaseModel):
    """The whole email was replaced, e.g. after an undo."""

    type: Literal["email_replaced"] = "email_replaced"
    email: Email


class BrandReadyEvent(BaseModel):
    """The scraper finished: the saved design system, and the conflicts to show to the user."""

    type: Literal["brand_ready"] = "brand_ready"
    brand_id: str
    design_system: DesignSystem
    conflicts: list[Conflict] = Field(default_factory=list)


class DoneEvent(BaseModel):
    """The run finished."""

    type: Literal["done"] = "done"
    cost_usd: float | None = None
    seconds: float


class ErrorEvent(BaseModel):
    """The run failed."""

    type: Literal["error"] = "error"
    message: str


StreamEvent = Annotated[
    StatusEvent
    | MessageEvent
    | SectionAddedEvent
    | SectionUpdatedEvent
    | SectionRemovedEvent
    | EmailReplacedEvent
    | BrandReadyEvent
    | DoneEvent
    | ErrorEvent,
    Field(discriminator="type"),
]


def to_sse(event: BaseModel | dict) -> ServerSentEvent:
    """One event on the wire. The SSE event name is its type, so a browser can listen per type."""
    data = event.model_dump(mode="json") if isinstance(event, BaseModel) else event
    return ServerSentEvent(data=data, event=data["type"])
