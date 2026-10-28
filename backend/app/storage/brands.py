"""Everything the backend keeps on disk for a brand.

Layout, under `<root>/brands/<brand_id>/`:

    design_system.json   the saved DesignSystem
    assets/              images the emails use
    raw/                 raw HTML + CSS from the website
    uploads/             files the user uploaded (PDF, images, past email HTML)

This is the only module that touches those files. A re-scrape replaces the design
system but never `user_notes`.
"""

import re
import secrets
from pathlib import Path
from typing import Any

from app.schemas.design_system import DesignSystem

SUBFOLDERS = ("assets", "raw", "uploads")
BRAND_ID_PATTERN = re.compile(r"[0-9a-f]{8}")


class BrandStore:
    """Files of every brand, under one root folder."""

    def __init__(self, root: Path) -> None:
        self._brands = root / "brands"
        self._brands.mkdir(parents=True, exist_ok=True)

    def create_brand(self) -> str:
        """Make a new brand folder with its subfolders. Returns the new brand_id."""
        brand_id = secrets.token_hex(4)
        for name in SUBFOLDERS:
            (self._brands / brand_id / name).mkdir(parents=True)
        return brand_id

    def brand_dir(self, brand_id: str) -> Path:
        """Folder of a brand. Raises if the id is not a known brand.

        The id must look like one we generated, which blocks paths such as '../x'.
        """
        folder = self._brands / brand_id
        if not BRAND_ID_PATTERN.fullmatch(brand_id) or not folder.is_dir():
            raise FileNotFoundError(f"Unknown brand: {brand_id}")
        return folder

    def load(self, brand_id: str) -> DesignSystem | None:
        """The saved design system, or None if the scraper has not run yet."""
        file = self.brand_dir(brand_id) / "design_system.json"
        if not file.exists():
            return None
        return DesignSystem.model_validate_json(file.read_text())

    def save(self, brand_id: str, design_system: DesignSystem) -> None:
        """Save a scraper result. Keeps the user_notes already saved, ignoring the new ones."""
        existing = self.load(brand_id)
        notes = existing.user_notes if existing else []
        self._write(brand_id, design_system.model_copy(update={"user_notes": notes}))

    def add_note(self, brand_id: str, note: str) -> None:
        """Append one confirmed preference to user_notes."""
        design_system = self.load(brand_id) or DesignSystem()
        design_system.user_notes.append(note)
        self._write(brand_id, design_system)

    def update_field(self, brand_id: str, path: str, value: Any) -> DesignSystem:
        """Set one field and return the new design system.

        `path` goes through objects with dots, e.g. 'css.buttons' or 'identity.name'.
        A list field such as 'colors' is replaced whole. Raises ValueError for an
        unknown path, and pydantic's ValidationError if the value has the wrong shape.
        """
        data = (self.load(brand_id) or DesignSystem()).model_dump()
        *parents, last = path.split(".")
        target = data
        for key in parents:
            if not isinstance(target, dict) or key not in target:
                raise ValueError(f"Unknown field: {path}")
            target = target[key]
        if not isinstance(target, dict) or last not in target:
            raise ValueError(f"Unknown field: {path}")
        target[last] = value

        design_system = DesignSystem.model_validate(data)
        self._write(brand_id, design_system)
        return design_system

    def _write(self, brand_id: str, design_system: DesignSystem) -> None:
        file = self.brand_dir(brand_id) / "design_system.json"
        file.write_text(design_system.model_dump_json(indent=2))
