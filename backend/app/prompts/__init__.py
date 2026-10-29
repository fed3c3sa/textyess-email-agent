"""All prompts live here as one `.md` file each, not inside Python code.

`render_system_prompt` fills a prompt's variables and returns the `SystemMessage`
for `create_agent`. `render_text` does the same for text that goes into a user
message. Variables are the only dynamic part (for example the design system as
JSON), so literal braces in a prompt's text must be doubled.
"""

from pathlib import Path

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate

PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str) -> ChatPromptTemplate:
    """Read prompts/<name>.md and wrap it as a single system message template."""
    text = (PROMPTS_DIR / f"{name}.md").read_text()
    return ChatPromptTemplate.from_messages([("system", text)])


def render_system_prompt(name: str, **variables: str) -> SystemMessage:
    """Fill a prompt's variables and return the system message. Raises if a variable is missing."""
    return load_prompt(name).format_messages(**variables)[0]


def render_text(name: str, **variables: str) -> str:
    """Fill a prompt's variables and return the text. Raises if a variable is missing."""
    text = (PROMPTS_DIR / f"{name}.md").read_text()
    return PromptTemplate.from_template(text).format(**variables)
