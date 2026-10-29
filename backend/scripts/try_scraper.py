"""Try the scraper on a real brand, with real keys. Run from backend/:

    .venv/bin/python -m scripts.try_scraper --url https://www.allbirds.com
    .venv/bin/python -m scripts.try_scraper --url https://www.allbirds.com guide.pdf logo.png

It creates a new brand in the data folder, copies the files into its uploads,
runs the scraper, and prints the design system, the conflicts and the time taken.
"""

import argparse
import asyncio
import shutil
import time

from app.agentic_infra.cost import CostCounter
from app.config import Settings
from app.agentic_infra.agents.scraper.agent import scrape_brand
from app.storage.brands import BrandStore


async def main(url: str | None, files: list[str]) -> None:
    settings = Settings()
    store = BrandStore(settings.data_dir)
    brand_id = store.create_brand()
    for file in files:
        shutil.copy(file, store.brand_dir(brand_id) / "uploads")

    start = time.time()
    cost = CostCounter()
    result = await scrape_brand(store, brand_id, url, settings, report=print, callbacks=[cost])

    print(result.model_dump_json(indent=2))
    print(f"Brand {brand_id} saved in {store.brand_dir(brand_id)}, in {time.time() - start:.0f} seconds, for ${cost.usd:.4f}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Try the scraper on a real brand.")
    parser.add_argument("--url", help="The brand's website.")
    parser.add_argument("files", nargs="*", help="Files to upload: PDFs, images, past emails as HTML.")
    args = parser.parse_args()
    asyncio.run(main(args.url, args.files))
