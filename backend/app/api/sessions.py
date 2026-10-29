"""Routes of the Studio screen: open a chat, send a message, read the current email."""

from collections.abc import AsyncIterable
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.api.dependencies import get_agent, known_brand
from app.agents.orchestrator.agent import stream_turn
from app.render import render_email
from app.schemas.api import ChatMessage
from app.schemas.email import Email
from app.schemas.events import to_sse

# Every route here checks the brand first, through the router's dependency.
router = APIRouter(prefix="/brands/{brand_id}/sessions", tags=["sessions"], dependencies=[Depends(known_brand)])


@router.post("")
def create_session() -> dict:
    return {"session_id": uuid4().hex}


@router.post("/{session_id}/messages", response_class=EventSourceResponse)
async def send_message(
    brand_id: str, session_id: str, message: ChatMessage, agent=Depends(get_agent)
) -> AsyncIterable[ServerSentEvent]:
    async for event in stream_turn(agent, session_id, brand_id, message.text, message.selected_section):
        yield to_sse(event)


@router.get("/{session_id}/email")
async def get_email(session_id: str, agent=Depends(get_agent)) -> dict:
    state = await agent.aget_state({"configurable": {"thread_id": session_id}})
    email = state.values.get("email") or Email()
    return {"email": email.model_dump(), "html": render_email(email)}
