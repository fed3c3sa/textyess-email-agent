"""Helpers shared by the test files. Pytest loads this file before every test."""

import pymupdf
import pytest

from app.storage.brands import BrandStore


def png(width: int, height: int) -> bytes:
    """A plain gray PNG image of the given size."""
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False)
    pixmap.clear_with(200)
    return pixmap.tobytes("png")


def make_pdf(path, pages: int):
    """A PDF whose first page holds a large logo and a small icon."""
    pdf = pymupdf.open()
    for number in range(pages):
        page = pdf.new_page()
        page.insert_text((72, 72), f"Acme brand guide, page {number + 1}.")
    pdf[0].insert_image(pymupdf.Rect(72, 100, 272, 300), stream=png(200, 200))  # logo: kept
    pdf[0].insert_image(pymupdf.Rect(72, 320, 92, 340), stream=png(20, 20))  # icon: skipped
    pdf.save(path)


@pytest.fixture
def store(tmp_path):
    return BrandStore(tmp_path)


@pytest.fixture
def brand_id(store):
    return store.create_brand()


@pytest.fixture
def brand_dir(store, brand_id):
    return store.brand_dir(brand_id)
