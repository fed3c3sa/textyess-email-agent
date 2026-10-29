"""The bodies of the API's requests."""

from typing import Any

from pydantic import BaseModel, Field


class LearnRequest(BaseModel):
    """Learn the brand from its website and from the files uploaded so far."""

    url: str | None = Field(default=None, description="The brand's website. Empty to read only the uploaded files.")


class FieldChange(BaseModel):
    """A correction of one field of the design system, made on the Setup screen."""

    field: str = Field(description="Dotted path of the field, e.g. 'identity.language' or 'colors'.")
    value: Any = Field(description="The new value. A list field such as 'colors' is replaced whole.")


class ChatMessage(BaseModel):
    """One message of the user in the Studio chat."""

    text: str = Field(description="What the user wrote.")
    selected_section: str | None = Field(
        default=None, description="Id of the section the user clicked in the preview, if any."
    )
