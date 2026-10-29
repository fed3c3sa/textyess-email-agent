"""Chat with the orchestrator in the terminal, and watch the events stream in. Run from backend/:

    .venv/bin/python -m scripts.try_chat                   # a new, empty brand: ask it to learn one
    .venv/bin/python -m scripts.try_chat --brand 0712b89a   # a brand the scraper already learned

Type a message and press Enter. Start it with '@hero ' to point at the section 'hero'.
After each turn the email is saved as email.html in the brand folder: open it in a
browser and refresh it after every turn. Type 'quit' to stop.
"""

import argparse
import asyncio
from uuid import uuid4

from app.config import Settings
from app.agents.orchestrator.agent import build_orchestrator, open_memory, stream_turn
from app.render import render_email
from app.schemas.email import Email
from app.storage.brands import BrandStore


def show(event: dict) -> None:
    """Print one event the way the Studio would show it."""
    match event["type"]:
        case "message":
            print(event["text"], end="", flush=True)
        case "status":
            print(f"\n  ... {event['text']}")
        case "section_added" | "section_updated":
            verb = "added" if event["type"] == "section_added" else "updated"
            section = event["section"]
            print(f"\n  [{verb} '{section['id']}'] why: {section['reasoning']}")
        case "section_removed":
            print(f"\n  [removed '{event['section_id']}']")
        case "email_replaced":
            print(f"\n  [email: {', '.join(s['id'] for s in event['email']['sections'])}]")
        case "done":
            print(f"  (done in {event['seconds']} s, ${event['cost_usd']})")
        case "error":
            print(f"\n  ERROR: {event['message']}")


async def main(brand_id: str | None) -> None:
    settings = Settings()
    store = BrandStore(settings.data_dir)
    brand_id = brand_id or store.create_brand()
    session_id = uuid4().hex
    page = store.brand_dir(brand_id) / "email.html"
    print(f"Brand {brand_id}. After each turn the email is saved in:\n  {page}")

    async with open_memory(settings.data_dir / "chat.sqlite") as memory:
        agent = build_orchestrator(store, settings, memory)
        while (text := input("\nyou> ").strip()) != "quit":
            if not text:  # an Enter pressed by mistake, or while the agent was working
                continue
            selected_section = None
            if text.startswith("@"):
                selected_section, _, text = text[1:].partition(" ")
            print("agent> ", end="")
            async for event in stream_turn(agent, session_id, brand_id, text, selected_section):
                show(event)
                if event["type"] == "email_replaced":
                    page.write_text(render_email(Email.model_validate(event["email"])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chat with the orchestrator in the terminal.")
    parser.add_argument("--brand", help="Id of an existing brand. Without it, a new empty brand is created.")
    asyncio.run(main(parser.parse_args().brand))
