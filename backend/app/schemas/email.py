"""The email as the agent builds it: an ordered list of sections.

The model decides which sections exist, what they are called and what they hold.
The only convention: the sections with id 'subject' and 'preheader' hold the subject
line and the preview text, as plain text. Every section carries its own reasoning,
and the agent edits sections by id, so a follow-up never restarts from a blank page.
`render_email()` turns an `Email` into the final HTML.
"""

from pydantic import BaseModel, Field


class Section(BaseModel):
    """One part of the email.

    `reasoning` is declared before `content` on purpose: the model writes fields
    in order, so it decides why before it writes the HTML, and the HTML follows
    from that decision.
    """

    id: str = Field(description="Short name of the part, chosen by the model, e.g. 'subject', 'hero', 'products'.")
    reasoning: str = Field(
        description="Why the agent made this part this way, in one or two sentences, shown to the user."
    )
    content: str = Field(
        description="Plain text for 'subject' and 'preheader'. Email HTML with inline CSS for every other part."
    )


class Email(BaseModel):
    """The current email, in display order."""

    sections: list[Section] = Field(default_factory=list, description="The sections, top to bottom.")
