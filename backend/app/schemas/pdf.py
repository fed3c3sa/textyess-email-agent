"""What is prepared from an uploaded PDF before the scraper runs."""

from pydantic import BaseModel, Field


class PdfContent(BaseModel):
    """The page images and the embedded images saved from one PDF."""

    page_count: int = Field(description="Number of pages in the PDF.")
    page_images: list[str] = Field(
        default_factory=list,
        description="Names of the page images saved in raw/, e.g. 'guide-page-1.png'. They are shown to the model.",
    )
    image_files: list[str] = Field(
        default_factory=list,
        description="Names of the images found inside the PDF and saved in assets/, e.g. 'guide-1.png'.",
    )
