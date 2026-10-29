"""Routes of the Setup screen: create a brand, upload files, learn it, read and correct its design system."""

import asyncio
import time
from collections.abc import AsyncIterable
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import ValidationError

from app.config import Settings
from app.api.dependencies import get_settings, get_store, known_brand
from app.schemas.api import FieldChange, LearnRequest
from app.schemas.design_system import DesignSystem
from app.schemas.events import BrandReadyEvent, DoneEvent, ErrorEvent, StatusEvent, to_sse
from app.agentic_infra.agents.scraper.agent import scrape_brand
from app.storage.brands import BrandStore

router = APIRouter(prefix="/brands", tags=["brands"])


@router.post("")
def create_brand(store: BrandStore = Depends(get_store)) -> dict:
    return {"brand_id": store.create_brand()}


@router.post("/{brand_id}/uploads")
async def upload_files(
    files: list[UploadFile], brand_id: str = Depends(known_brand), store: BrandStore = Depends(get_store)
) -> dict:
    names = []
    for file in files:
        name = Path(file.filename or "upload").name
        (store.brand_dir(brand_id) / "uploads" / name).write_bytes(await file.read())
        names.append(name)
    return {"files": names}


@router.post("/{brand_id}/learn", response_class=EventSourceResponse)
async def learn(
    request: LearnRequest,
    brand_id: str = Depends(known_brand),
    store: BrandStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> AsyncIterable[ServerSentEvent]:
    events: asyncio.Queue = asyncio.Queue()  # the scraper puts events in, this stream takes them out
    start = time.time()

    def report(text: str) -> None:
        events.put_nowait(StatusEvent(text=text))

    async def run() -> None:
        try:
            result = await scrape_brand(store, brand_id, request.url, settings, report)
            await events.put(BrandReadyEvent(brand_id=brand_id, **result.model_dump()))
            await events.put(DoneEvent(seconds=round(time.time() - start, 1)))
        except Exception as error:
            await events.put(ErrorEvent(message=str(error)))
        await events.put(None)  # the end of the stream

    task = asyncio.create_task(run())
    while (event := await events.get()) is not None:
        yield to_sse(event)
    await task


@router.get("/{brand_id}")
def get_design_system(brand_id: str = Depends(known_brand), store: BrandStore = Depends(get_store)) -> DesignSystem:
    return store.load(brand_id) or DesignSystem()


@router.patch("/{brand_id}")
def change_field(
    change: FieldChange, brand_id: str = Depends(known_brand), store: BrandStore = Depends(get_store)
) -> DesignSystem:
    try:
        return store.update_field(brand_id, change.field, change.value)
    except (ValueError, ValidationError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/{brand_id}/files/{folder}/{name}")
def get_file(
    folder: Literal["assets", "uploads"],
    name: str,
    brand_id: str = Depends(known_brand),
    store: BrandStore = Depends(get_store),
) -> FileResponse:
    """An image for the preview, from the brand's assets or uploads."""
    path = store.brand_dir(brand_id) / folder / Path(name).name
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"No file {folder}/{name}")
    return FileResponse(path)
