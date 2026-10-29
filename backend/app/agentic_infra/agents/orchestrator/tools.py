"""The orchestrator's tools: write the email, remember a preference, correct or learn the brand.

The email lives in the agent's state. `put_section` and `drop_section` are plain
functions that return a new email, so they can be tested without a model. The
tools never save the whole email: they save one edit with `Command(update=...)`,
which `apply_email_edit` applies to the state, and they send an SSE event so the
preview changes while the agent works. The session's brand comes from the run's
context.
"""

from dataclasses import dataclass
from typing import Annotated, Any, NotRequired

from langchain.agents import AgentState
from langchain.tools import BaseTool, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from pydantic import ValidationError

from app.config import Settings
from app.schemas.email import Email, Section
from app.schemas.events import SectionAddedEvent, SectionRemovedEvent, SectionUpdatedEvent, StatusEvent
from app.agentic_infra.agents.scraper.agent import scrape_brand
from app.storage.brands import BrandStore


@dataclass
class OrchestratorContext:
    """Fixed for a whole run: the brand of the chat session."""

    brand_id: str


def put_section(email: Email, section: Section, position: int | None) -> tuple[Email, int]:
    """The email with `section` written in, replacing the section with the same id if there is one.

    With no position, a replaced section stays where it was and a new one goes at the end.
    Returns the new email and the section's position.
    """
    old_position = next((i for i, s in enumerate(email.sections) if s.id == section.id), None)
    sections = [s for s in email.sections if s.id != section.id]
    if position is None:
        position = old_position if old_position is not None else len(sections)
    position = max(0, min(position, len(sections)))
    sections.insert(position, section)
    return Email(sections=sections), position


def drop_section(email: Email, section_id: str) -> Email:
    """The email without the section `section_id`. An unknown id changes nothing."""
    return Email(sections=[s for s in email.sections if s.id != section_id])


def apply_email_edit(email: Email, edit: dict) -> Email:
    """How the `email` field of the state changes: one edit at a time.

    An edit is {"write": section, "position": n} or {"remove": section_id}. When the
    model calls several tools at once, LangGraph applies their edits one after the
    other, so none is lost.
    """
    if "remove" in edit:
        return drop_section(email, edit["remove"])
    new_email, _ = put_section(email, Section.model_validate(edit["write"]), edit.get("position"))
    return new_email


class OrchestratorState(AgentState):
    """The agent's state: the chat messages, plus the current email, changed only through `apply_email_edit`."""

    email: NotRequired[Annotated[Email, apply_email_edit]]


def reply(runtime: ToolRuntime, text: str) -> ToolMessage:
    """The tool's answer to the model."""
    return ToolMessage(content=text, tool_call_id=runtime.tool_call_id)


def build_orchestrator_tools(store: BrandStore, settings: Settings) -> list[BaseTool]:
    """The orchestrator's tools, bound to the brand store and the settings."""

    @tool(parse_docstring=True)
    def write_section(
        section_id: str, reasoning: str, content: str, runtime: ToolRuntime[OrchestratorContext], position: int | None = None
    ) -> Command:
        """Write one part of the email: add it, or replace it if a part with this id exists.

        The email is a list of parts, top to bottom, which the user sees in a preview.
        The parts 'subject' and 'preheader' are the subject line and the preview text,
        as plain text. Every other part is email HTML with inline CSS.

        Args:
            section_id: Short name of the part, e.g. 'subject', 'hero', 'products'. Reuse an id to replace that part.
            reasoning: Why you made this part this way, in one or two sentences the user reads.
            content: Plain text for 'subject' and 'preheader'; HTML with inline CSS for every other part.
            position: Where the part goes, counting from 0. Leave it empty to keep a part where it is, or to add a new part at the end.
        """
        email = runtime.state.get("email") or Email()
        exists = any(s.id == section_id for s in email.sections)
        section = Section(id=section_id, reasoning=reasoning, content=content)
        _, index = put_section(email, section, position)

        event = SectionUpdatedEvent if exists else SectionAddedEvent
        runtime.stream_writer(event(section=section, index=index).model_dump())
        text = f"Wrote '{section_id}' at position {index}."
        edit = {"write": section.model_dump(), "position": position}
        return Command(update={"email": edit, "messages": [reply(runtime, text)]})

    @tool(parse_docstring=True)
    def remove_section(section_id: str, runtime: ToolRuntime[OrchestratorContext]) -> Command | str:
        """Take a part out of the email.

        Args:
            section_id: The id of the part to remove.
        """
        email = runtime.state.get("email") or Email()
        if not any(s.id == section_id for s in email.sections):
            ids = ", ".join(s.id for s in email.sections) or "none"
            return f"There is no section '{section_id}'. Sections: {ids}."

        runtime.stream_writer(SectionRemovedEvent(section_id=section_id).model_dump())
        edit = {"remove": section_id}
        return Command(update={"email": edit, "messages": [reply(runtime, f"Removed '{section_id}'.")]})

    @tool(parse_docstring=True)
    def save_note(note: str, runtime: ToolRuntime[OrchestratorContext]) -> str:
        """Remember a preference of the user for every future email of this brand. Call it only after the user said yes.

        Args:
            note: The preference as one plain sentence, e.g. 'Never use emojis in the subject line.'
        """
        store.add_note(runtime.context.brand_id, note)
        return "Saved. Every future email will follow it."

    @tool(parse_docstring=True)
    def update_design_system(field: str, value: Any, runtime: ToolRuntime[OrchestratorContext]) -> str:
        """Change one field of the brand's design system, for this and every future email.

        Args:
            field: Dotted path of the field, e.g. 'identity.language' or 'colors'. A list field is replaced whole.
            value: The new value: a text, or the whole new list for a list field such as 'colors'.
        """
        if field.split(".")[0] == "user_notes":
            return "User notes cannot be changed here. Use save_note to add one."
        try:
            store.update_field(runtime.context.brand_id, field, value)
        except (ValueError, ValidationError) as error:
            return f"Could not change {field}: {error}"
        return f"Changed {field}."

    @tool(parse_docstring=True)
    async def learn_brand(runtime: ToolRuntime[OrchestratorContext], url: str | None = None) -> str:
        """Learn the brand from its website and from the files the user uploaded in this chat.

        It takes about a minute. What it learns is added to the brand's design system.

        Args:
            url: The brand's website, starting with http:// or https://. Leave it empty to read only the uploaded files.
        """

        def report(text: str) -> None:
            runtime.stream_writer(StatusEvent(text=text).model_dump())

        try:
            result = await scrape_brand(store, runtime.context.brand_id, url, settings, report)
        except Exception as error:
            return f"Could not learn the brand: {error}"

        lines = ["Learned the brand. The design system is updated."]
        for conflict in result.conflicts:
            lines.append(
                f"Conflict on {conflict.field}: the website says {conflict.website_value}, "
                f"the document says {conflict.document_value}. The document value is used; tell the user."
            )
        return "\n".join(lines)

    return [write_section, remove_section, save_note, update_design_system, learn_brand]
