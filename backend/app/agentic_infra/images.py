"""Images for the model: the agents attach them to a user message, the only place every model can see them."""

import base64
import io
from pathlib import Path

from PIL import Image

from app.config import MAX_IMAGE_WIDTH, MAX_IMAGES_TO_MODEL

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}  # SVG is left out: models cannot see it


def image_block(path: Path) -> dict | None:
    """The image as a PNG content block, at most MAX_IMAGE_WIDTH wide. None if it cannot be read."""
    try:
        image = Image.open(path)
        image.thumbnail((MAX_IMAGE_WIDTH, MAX_IMAGE_WIDTH * 10))  # shrinks, keeping the proportions
        if image.mode not in ("RGB", "RGBA"):  # e.g. CMYK or a palette
            image = image.convert("RGBA")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
    except Exception:
        return None
    data = base64.b64encode(buffer.getvalue()).decode()
    return {"type": "image", "base64": data, "mime_type": "image/png"}


def labelled_image_blocks(images: list[tuple[str, Path]]) -> list[dict]:
    """Content blocks for a user message: each image right after its label, up to MAX_IMAGES_TO_MODEL.

    `images` are (label, path) pairs, e.g. ("/uploads/logo.png", path). Files that are not
    images, or cannot be read, are skipped.
    """
    blocks = []
    for label, path in images:
        if len(blocks) == 2 * MAX_IMAGES_TO_MODEL:  # two blocks per image: label and image
            break
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        block = image_block(path)
        if block:
            blocks += [{"type": "text", "text": f"{label}:"}, block]
    return blocks

