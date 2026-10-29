"""Settings, read from the environment or from the `.env` file at the root of the repository."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Keys and knobs of the backend."""

    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env")

    openrouter_api_key: str = Field(description="Key for OpenRouter, which serves the language model.")
    firecrawl_api_key: str = Field(description="Key for Firecrawl, which reads websites.")
    model: str = Field(default="z-ai/glm-5.3-flash", description="OpenRouter id of the model used by every agent.")
    data_dir: Path = Field(default=Path("data"), description="Folder for brands and the chat database.")
    scraper_max_steps: int = Field(
        default=30, description="Most graph steps the scraper may take before it is stopped."
    )
