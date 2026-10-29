"""What the routes receive through `Depends`: the objects created once at startup, and the brand check.

The settings, the brand store and the orchestrator agent live in `app.state`
(see `main.py`). Routes ask for them by type, and tests can build an app with
their own settings.
"""

from fastapi import Depends, HTTPException, Request

from app.config import Settings
from app.storage.brands import BrandStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> BrandStore:
    return request.app.state.store


def get_agent(request: Request):
    """The orchestrator agent, built at startup with its memory."""
    return request.app.state.agent


def known_brand(brand_id: str, store: BrandStore = Depends(get_store)) -> str:
    """Checks the brand exists before the route runs, so a stream never starts for an unknown brand."""
    try:
        store.brand_dir(brand_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return brand_id
