"""The email as the agent builds it: an ordered list of sections.

Subject and preheader are sections too, so each one streams and carries its own
reasoning. The agent edits sections by `id`, so a follow-up never restarts from a
blank page. `render_email()` turns an `Email` into the final HTML.
"""

from typing import Literal

from pydantic import BaseModel, Field

SectionKind = Literal["subject", "preheader", "header", "hero", "text", "cta", "footer"]


class Section(BaseModel):
    """One part of the email.

    `reasoning` is declared before `content` on purpose: the model writes fields
    in order, so it decides why before it writes the HTML, and the HTML follows
    from that decision.
    """

    id: str = Field(description="Stable handle used to update or remove this section.")
    kind: SectionKind = Field(description="Which part of the email this is.")
    reasoning: str = Field(
        description="Why the agent made this part this way, in one or two sentences, shown to the user."
    )
    content: str = Field(
        description="Email-safe HTML for body parts. Plain text for the subject and the preheader."
    )


class Email(BaseModel):
    """The current email, in display order."""

    sections: list[Section] = Field(default_factory=list, description="The sections, top to bottom.")
