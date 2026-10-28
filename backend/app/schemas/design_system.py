"""Pydantic models for the brand design system.

`DesignSystem` is the structured output of the scraper and the only brand input
the orchestrator reads. Every field has a default, because a sparse website may
fill almost nothing. `ScrapeResult` also carries the transient `conflicts`.

The `description` of each field is part of the JSON schema sent to the model, so
it doubles as an instruction for the scraper.
"""

from typing import Literal

from pydantic import BaseModel, Field


class Identity(BaseModel):
    """Who the brand is."""

    name: str | None = Field(default=None, description="Brand name.")
    source_url: str | None = Field(default=None, description="Main website URL of the brand.")
    language: str | None = Field(
        default=None, description="Language the brand writes in, as a code, e.g. 'en' or 'it'."
    )
    description: str | None = Field(
        default=None, description="One or two sentences on what the brand does and sells."
    )


class ColorToken(BaseModel):
    """One named brand color."""

    role: str = Field(
        description="What the color is used for: primary, background, text, cta, link, accent..."
    )
    hex: str = Field(description="Color as a hex code, e.g. '#E4002B'.")


class Font(BaseModel):
    """The font family used for one role."""

    role: Literal["heading", "body"] = Field(description="Where the font is used.")
    family: str = Field(description="Font family name, e.g. 'Helvetica Neue'.")


class CssRules(BaseModel):
    """Distilled CSS declarations per element. Not the raw dump (that stays in raw/)."""

    body: str = Field(default="", description="Declarations for body text, e.g. 'color:#111;font-size:16px'.")
    headings: str = Field(default="", description="Declarations for h1-h3.")
    links: str = Field(default="", description="Declarations for links.")
    buttons: str = Field(default="", description="Declarations for call-to-action buttons.")
    container: str = Field(
        default="", description="Declarations for the main content container (background, padding, border)."
    )


class Voice(BaseModel):
    """How the brand sounds."""

    tone: list[str] = Field(
        default_factory=list, description="Adjectives describing the tone, e.g. 'playful', 'direct'."
    )
    dos: list[str] = Field(default_factory=list, description="Writing habits to follow.")
    donts: list[str] = Field(default_factory=list, description="Writing habits and words to avoid.")
    sample_phrases: list[str] = Field(
        default_factory=list, description="Real phrases from the brand that show its voice."
    )


class HtmlSnippet(BaseModel):
    """A reference snippet of the brand's HTML, not a full page."""

    kind: Literal["header", "hero", "cta", "footer"] = Field(description="Which part of an email it shows.")
    html: str = Field(description="The snippet's HTML. Keep it short.")


class Asset(BaseModel):
    """An image the email can use."""

    description: str = Field(description="What the image shows and when to use it.")
    role: Literal["logo", "hero", "product", "icon", "other"] = Field(description="Kind of image.")
    pointer: str = Field(description="Public URL of the image, or its path inside the brand's assets folder.")


class EmailConstraints(BaseModel):
    """Rules for email-safe HTML, separate from the website's CSS."""

    width_px: int = Field(default=600, description="Width of the email's main table in pixels.")
    footer_legal: str | None = Field(
        default=None, description="Text the footer must always contain (address, unsubscribe line...)."
    )


class DesignSystem(BaseModel):
    """Everything the agent knows about how a brand looks and sounds."""

    identity: Identity = Field(default_factory=Identity, description="Who the brand is.")
    colors: list[ColorToken] = Field(default_factory=list, description="The brand color palette.")
    css: CssRules = Field(default_factory=CssRules, description="Distilled CSS rules for the main elements.")
    fonts: list[Font] = Field(default_factory=list, description="Fonts for headings and body text.")
    voice: Voice = Field(default_factory=Voice, description="How the brand sounds.")
    guidelines: str = Field(
        default="", description="Free-text design guidelines: layout, spacing, imagery, what to avoid."
    )
    html_examples: list[HtmlSnippet] = Field(
        default_factory=list, description="Short HTML snippets (header, hero, cta, footer) from the brand."
    )
    assets: list[Asset] = Field(default_factory=list, description="Images the emails can use.")
    email_constraints: EmailConstraints = Field(
        default_factory=EmailConstraints, description="Rules for email-safe HTML."
    )
    user_notes: list[str] = Field(
        default_factory=list,
        description="Preferences the user asked to keep for future emails. The scraper leaves this empty.",
    )


class Conflict(BaseModel):
    """Website and document disagree on one field. The document value is used."""

    field: str = Field(description="Dotted path of the field, e.g. 'colors.primary'.")
    website_value: str = Field(description="Value found on the website.")
    document_value: str = Field(description="Value found in the uploaded document.")


class ScrapeResult(BaseModel):
    """What the scraper returns: the design system plus transient conflicts."""

    design_system: DesignSystem = Field(description="The design system built from all sources.")
    conflicts: list[Conflict] = Field(
        default_factory=list, description="Fields where the website and a document disagree."
    )
