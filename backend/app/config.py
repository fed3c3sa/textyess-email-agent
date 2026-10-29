"""Settings, read from the environment or from the `.env` file at the root of the repository."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

# Limits on what goes to the model, so a big website or PDF cannot blow up the request.
MAX_IMAGES_TO_MODEL = 10  # images downloaded from a website, and images attached to the scraper's message
MAX_PAGE_CHARS = 50_000  # characters kept from the website's HTML and from its text
MAX_PDF_PAGES = 10  # pages of each PDF turned into images
MAX_IMAGE_WIDTH = 1024  # wider images are shrunk before they go to the model
SUMMARY_TEXT_CHARS = 1_500  # characters of the website's text shown in the scraper's message
SCRAPER_MAX_MODEL_CALLS = 10  # model calls the scraper may make while searching, before it must answer


class Settings(BaseSettings):
    """Keys and knobs of the backend."""

    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env")

    openrouter_api_key: str = Field(description="Key for OpenRouter, which serves the language model.")
    firecrawl_api_key: str = Field(description="Key for Firecrawl, which reads websites.")
    model: str = Field(default="z-ai/glm-5.3-flash", description="OpenRouter id of the model used by every agent.")
    reasoning_effort: Literal["xhigh", "high", "medium", "low", "minimal", "none"] = Field(
        default="low",
        description="How much the model thinks before answering. Less is faster",
    )
    data_dir: Path = Field(
        default=REPO_ROOT / "backend" / "data", description="Folder for brands and the chat database."
    )
    public_url: str = Field(
        default="http://localhost:8000", description="Address of the API, used to link the images saved on disk."
    )
