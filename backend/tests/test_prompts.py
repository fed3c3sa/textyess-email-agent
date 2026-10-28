import pytest
from langchain_core.messages import SystemMessage

from app.prompts import load_prompt, render_system_prompt


def test_each_prompt_declares_the_variables_we_fill():
    """If a prompt gains or loses a variable, the code that fills it must change too."""
    assert load_prompt("scraper_system").input_variables == []
    assert sorted(load_prompt("orchestrator_system").input_variables) == ["current_email", "design_system"]


def test_render_fills_the_variables():
    message = render_system_prompt(
        "orchestrator_system", design_system='{"identity": {"name": "Acme"}}', current_email="NO EMAIL YET"
    )
    assert isinstance(message, SystemMessage)
    assert '"name": "Acme"' in message.content
    assert "NO EMAIL YET" in message.content
    assert "{design_system}" not in message.content


def test_render_without_variables_for_a_static_prompt():
    assert "design system" in render_system_prompt("scraper_system").content


def test_missing_variable_raises():
    with pytest.raises(KeyError):
        render_system_prompt("orchestrator_system", design_system="{}")
