"""Unit tests for AURA Loader widget."""
import pytest
from aura.ui.widgets.loader import AURALoader, GRADIENT_PALETTE, SPINNER_FRAMES


def test_loader_init_and_frames():
    loader_grad = AURALoader(text="Thinking...", style="gradient")
    assert loader_grad.loader_style == "gradient"
    frame_grad = loader_grad._render_frame()
    assert "Thinking..." in frame_grad.plain

    loader_spin = AURALoader(text="Assessing", style="spinner")
    assert loader_spin.loader_style == "spinner"
    frame_spin = loader_spin._render_frame()
    assert "Assessing" in frame_spin.plain
    assert any(ch in frame_spin.plain for ch in SPINNER_FRAMES)

    loader_min = AURALoader(text="Executing", style="minimal")
    assert loader_min.loader_style == "minimal"
    frame_min = loader_min._render_frame()
    assert "Executing" in frame_min.plain


def test_loader_text_update():
    loader = AURALoader(text="Initial", style="spinner")
    loader.set_text("Updated state")
    assert loader.text_label == "Updated state"
    assert "Updated state" in loader._render_frame().plain
