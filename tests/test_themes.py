from __future__ import annotations

import ast
from copy import deepcopy
from pathlib import Path

import customtkinter as ctk
import pytest

from record_transcript_resume.themes import (
    DEFAULT_THEME, LEGACY_COLOR_ROLES, THEMES, ThemeColor,
    configure_widget_defaults, role_color, theme_color, theme_colors,
)


def test_repeated_switches_preserve_roles_and_restore_original_violet_colors() -> None:
    # Several light-theme surfaces intentionally share a color. Reverse RGB
    # matching cannot recover which original surface each control needs.
    original = [theme_color(value, DEFAULT_THEME) for value in LEGACY_COLOR_ROLES]
    current = original
    for name in [*THEMES, *reversed(THEMES), *THEMES]:
        current = [theme_color(value, name) for value in current]
        for before, after in zip(original, current):
            assert isinstance(after, ThemeColor)
            assert after.role == before.role
            assert after.original == before.original
            assert after == before.for_theme(name)
    current = [theme_color(value, DEFAULT_THEME) for value in current]
    assert current == original


def test_equal_rgb_values_do_not_collapse_distinct_roles() -> None:
    text = role_color("text", "claro")
    foreground = role_color("accent_text", "claro")
    assert theme_color(text, "oceano") == THEMES["oceano"]["text"]
    assert theme_color(foreground, "oceano") == THEMES["oceano"]["accent_text"]
    assert text.role != foreground.role
    assert theme_color("transparent", "claro") == "transparent"
    assert theme_color("#010203", "claro") == "#010203"
    assert theme_color("#123456", "claro") == "#123456"


def test_every_original_gui_color_has_a_reviewed_role() -> None:
    source = Path(__file__).parents[1] / "src/record_transcript_resume/gui.py"
    tree = ast.parse(source.read_text(encoding="utf-8-sig"))
    literals = {
        argument.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "_theme_color"
        for argument in node.args
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
    }
    assert literals - LEGACY_COLOR_ROLES.keys() == set()


def test_control_defaults_keep_geometry_and_bind_disabled_and_dropdown_colors() -> None:
    template = deepcopy(ctk.ThemeManager.theme)
    before = deepcopy(template)
    configure_widget_defaults(template, "machine_red")
    for name, options in before.items():
        for key, value in options.items():
            if "color" not in key:
                assert template[name][key] == value
    assert template["CTkButton"]["text_color_disabled"].role == "muted"
    assert template["DropdownMenu"]["text_color"].role == "text"
    assert template["CTkSlider"]["button_color"].role == "accent"


@pytest.mark.parametrize("name", THEMES)
def test_palette_roles_have_readable_foregrounds(name: str) -> None:
    from record_transcript_resume.themes import _contrast

    palette = theme_colors(name)
    assert _contrast(palette["text"], palette["surface"]) >= 7
    assert _contrast(palette["text"], palette["surface_input"]) >= 7
    assert _contrast(palette["muted"], palette["surface"]) >= 4.5
    assert _contrast(palette["accent_text"], palette["accent"]) >= 4.5
    assert _contrast(palette["text"], palette["surface_button"]) >= 4.5


@pytest.mark.parametrize("name", THEMES)
def test_background_update_result_keeps_the_primary_button_readable(name: str, monkeypatch) -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock
    from record_transcript_resume import gui
    from record_transcript_resume.themes import _contrast

    monkeypatch.setattr(gui, "_COLORS", theme_colors(name))
    app = SimpleNamespace(
        _update_check_running=True, _available_update=None,
        update_hint=Mock(), update_check_button=Mock(), update_apply_button=Mock(),
    )
    gui.RecorderApp._on_update_checked(app, SimpleNamespace(available=False, message="Atualizado"))
    colors = app.update_check_button.configure.call_args.kwargs
    assert _contrast(colors["text_color"], colors["fg_color"]) >= 4.5


@pytest.mark.parametrize("name", THEMES)
def test_cached_native_tooltip_uses_the_current_palette(name: str, monkeypatch) -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock
    from record_transcript_resume import gui

    monkeypatch.setattr(gui, "_ACTIVE_THEME_NAME", name)
    popup = Mock()
    popup.winfo_reqwidth.return_value = 150
    popup.winfo_reqheight.return_value = 40
    label = Mock()
    button = SimpleNamespace(
        winfo_exists=lambda: True, winfo_ismapped=lambda: True,
        winfo_rootx=lambda: 0, winfo_rooty=lambda: 0,
        winfo_width=lambda: 80, winfo_height=lambda: 40,
    )
    app = SimpleNamespace(
        _button_tooltip_target=button, _button_tooltip_popup=popup,
        _button_tooltip_label=label, _button_tooltip_after=None,
        winfo_pointerxy=lambda: (10, 10), _button_help_text=lambda _: "Ajuda do botão",
        _monitor_bounds_at=lambda *_: (0, 0, 1920, 1080),
        _geometry_string=lambda *values: "150x40+24+30",
    )
    gui.RecorderApp._show_button_tooltip(app)

    colors = label.configure.call_args.kwargs
    assert colors["bg"] == theme_color("#263550", name)
    assert colors["fg"] == theme_color("#F1F5FB", name)
    popup.deiconify.assert_called_once()


@pytest.mark.parametrize("name", THEMES)
@pytest.mark.parametrize("already_current", [False, True])
def test_native_backing_color_is_ready_before_mapping(name: str, already_current: bool, monkeypatch) -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock
    from record_transcript_resume import gui

    color = theme_colors(name)["surface_panel"]
    widget = SimpleNamespace(cget=Mock(return_value=color), _apply_appearance_mode=lambda value: value)
    native_configure = Mock()
    monkeypatch.setattr(gui.tk.Frame, "cget", lambda *_: color.lower() if already_current else "#000000")
    monkeypatch.setattr(gui.tk.Frame, "configure", native_configure)

    gui.RecorderApp._sync_native_theme_background(widget)

    widget.cget.assert_called_once_with("bg_color")
    if already_current:
        native_configure.assert_not_called()
    else:
        native_configure.assert_called_once_with(widget, background=color)


@pytest.mark.parametrize("width, columns", [(180, 1), (360, 2), (540, 3), (660, 3), (1280, 3)])
def test_theme_picker_fills_three_by_three_and_keeps_cached_layout(width: int, columns: int) -> None:
    from types import SimpleNamespace
    from unittest.mock import Mock
    from record_transcript_resume import gui

    buttons = {name: Mock() for name in THEMES}
    app = SimpleNamespace(_theme_choice_buttons=buttons, _theme_choice_grid=Mock())
    gui.RecorderApp._layout_theme_choices(app, width)
    gui.RecorderApp._layout_theme_choices(app, width)

    assert app._theme_choice_columns == columns
    for index, button in enumerate(buttons.values()):
        button.grid.assert_called_once_with(
            row=index // columns, column=index % columns, sticky="ew", padx=3, pady=3,
        )
