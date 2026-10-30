"""Images for the model: shrinking, reading every format, and the labelled blocks of a user message."""

import base64
import io

from PIL import Image

from app.agentic_infra.shared.images import image_block, labelled_image_blocks
from app.config import MAX_IMAGE_WIDTH, MAX_IMAGES_TO_MODEL
from tests.conftest import png


def test_wide_images_are_shrunk(tmp_path):
    path = tmp_path / "wide.png"
    path.write_bytes(png(3000, 1000))

    block = image_block(path)

    width = Image.open(io.BytesIO(base64.b64decode(block["base64"]))).width
    assert width <= MAX_IMAGE_WIDTH


def test_webp_images_are_read(tmp_path):
    """Many shops serve their images as WebP."""
    path = tmp_path / "photo.webp"
    Image.new("RGB", (50, 50), "red").save(path, format="WEBP")
    assert image_block(path)["mime_type"] == "image/png"


def test_a_broken_image_is_skipped(tmp_path):
    path = tmp_path / "broken.png"
    path.write_bytes(b"not an image")
    assert image_block(path) is None


def test_each_image_comes_after_its_label_and_the_rest_is_skipped(tmp_path):
    images = []
    for number in range(MAX_IMAGES_TO_MODEL + 3):
        path = tmp_path / f"image-{number}.png"
        path.write_bytes(png(10, 10))
        images.append((f"/assets/{path.name}", path))
    (tmp_path / "logo.svg").write_text("<svg/>")
    images.insert(0, ("/assets/logo.svg", tmp_path / "logo.svg"))  # models cannot see SVG

    blocks = labelled_image_blocks(images)

    assert blocks[0] == {"type": "text", "text": "/assets/image-0.png:"}
    assert blocks[1]["type"] == "image"
    assert len(blocks) == 2 * MAX_IMAGES_TO_MODEL  # stops at the limit
