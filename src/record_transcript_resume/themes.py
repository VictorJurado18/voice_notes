"""Built-in palettes and stable semantic color bindings for the UI.

ThemeColor keeps the role alongside its Tk-compatible string value. Switching
themes resolves that role again, never a nearest color from the last palette.
"""
from __future__ import annotations

from functools import lru_cache


THEME_LABELS: dict[str, str] = {
    "violeta": "Violeta atual",
    "oceano": "Oceano",
    "floresta": "Floresta",
    "ambar": "Âmbar",
    "vinho": "Vinho",
    "machine_red": "Machine Red",
    "claro": "Claro",
    "grafite": "Grafite",
}
DEFAULT_THEME = "violeta"


def _rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]


def _mix(a: str, b: str, amount: float) -> str:
    left = tuple(int(a[index:index + 2], 16) for index in (1, 3, 5))
    right = tuple(int(b[index:index + 2], 16) for index in (1, 3, 5))
    values = tuple(round(x + (y - x) * amount) for x, y in zip(left, right))
    return "#" + "".join(f"{value:02X}" for value in values)


def _luminance(color: str) -> float:
    channels = [value / 255 for value in _rgb(color)]
    linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in channels]
    return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    lighter, darker = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (lighter + .05) / (darker + .05)


def _palette(
    *, bg: str, surface: str, surface_alt: str, border: str, text: str,
    muted: str, soft: str, accent: str, accent_hover: str, success: str,
    warning: str, danger: str, brand: str | None = None,
    brand_muted: str | None = None, success_hover: str | None = None,
    danger_hover: str | None = None,
) -> dict[str, str]:
    """Build a consistent family of related surface and control colors."""
    dark = sum(int(bg[index:index + 2], 16) for index in (1, 3, 5)) < 360
    base = {
        "bg": bg, "surface": surface, "surface_alt": surface_alt,
        "border": border, "text": text, "muted": muted, "soft": soft,
        "text_soft": soft,
        "brand": brand or soft, "brand_muted": brand_muted or muted,
        "accent": accent, "accent_hover": accent_hover,
        "accent_text": "#111318" if _contrast(accent, "#111318") > _contrast(accent, "#FFFFFF") else "#FFFFFF",
        "success": success, "success_hover": success_hover or _mix(success, text, .14),
        "danger": danger, "danger_hover": danger_hover or _mix(danger, text, .14),
        "warning": warning, "white": "#FFFFFF", "black": "#000000",
    }
    if dark:
        base.update({
            "surface_deep": _mix(bg, surface, .28),
            "surface_panel": _mix(surface, surface_alt, .20),
            "surface_panel_alt": _mix(surface_alt, surface, .24),
            "surface_tile": _mix(surface, surface_alt, .44),
            "surface_elevated": _mix(surface_alt, accent, .045),
            "surface_button": _mix(surface_alt, accent, .12),
            "surface_button_hover": _mix(surface_alt, accent, .24),
            "surface_action": _mix(surface, accent, .31),
            "surface_action_hover": _mix(surface, accent, .45),
            "surface_input": _mix(bg, surface, .16),
            "border_input": _mix(border, soft, .10),
            "selection": _mix(surface_alt, accent, .22),
            "selection_full": _mix(surface_alt, accent, .32),
            "accent_soft": _mix(surface, accent, .20),
            "accent_mid": _mix(accent, accent_hover, .45),
            "accent_light": _mix(accent_hover, soft, .30),
            "success_soft": _mix(surface, success, .18),
            "danger_soft": _mix(surface, danger, .18),
            "warning_soft": _mix(surface, warning, .18),
        })
    else:
        base.update({
            "surface_deep": _mix(bg, surface, .32),
            "surface_panel": _mix(surface, surface_alt, .52),
            "surface_panel_alt": _mix(surface_alt, surface, .32),
            "surface_tile": _mix(surface, surface_alt, .66),
            "surface_elevated": _mix(surface_alt, accent, .035),
            "surface_button": _mix(surface_alt, accent, .10),
            "surface_button_hover": _mix(surface_alt, accent, .18),
            "surface_action": _mix(surface, accent, .26),
            "surface_action_hover": _mix(surface, accent, .34),
            "surface_input": surface,
            "border_input": _mix(border, muted, .24),
            "selection": _mix(surface_alt, accent, .10),
            "selection_full": _mix(surface_alt, accent, .16),
            "accent_soft": _mix(surface, accent, .10),
            "accent_mid": _mix(accent, accent_hover, .45),
            "accent_light": _mix(accent_hover, text, .50),
            "success_soft": _mix(surface, success, .10),
            "danger_soft": _mix(surface, danger, .10),
            "warning_soft": _mix(surface, warning, .12),
        })
    # The chroma key is an intentional sentinel used by the native window
    # rounding code; it must never be shifted with the rest of the palette.
    base["transparent"] = "#010203"
    return base


THEMES: dict[str, dict[str, str]] = {
    "violeta": _palette(
        bg="#080C16", surface="#101827", surface_alt="#162136", border="#283754",
        text="#F6F8FF", muted="#AAB8D4", soft="#C9D3FF", brand="#D3DCF3",
        brand_muted="#8FA1C9", accent="#6656D8", accent_hover="#7162DD",
        success="#55D6A0", success_hover="#70E4B4", warning="#F5B942",
        danger="#F17A91", danger_hover="#FF92A6",
    ),
    "oceano": _palette(
        bg="#07131B", surface="#0D1D28", surface_alt="#132B39", border="#285062",
        text="#F1FBFF", muted="#A8C5D0", soft="#C8E3EB", accent="#11A6BC",
        accent_hover="#29BED0", success="#58D6B2", warning="#F3C369", danger="#FF8D91",
    ),
    "floresta": _palette(
        bg="#0C1511", surface="#131F19", surface_alt="#1A2A21", border="#35513D",
        text="#F3FBF2", muted="#B0C8B1", soft="#D3E6D2", accent="#4DA76C",
        accent_hover="#64BC80", success="#83D9A0", warning="#EEC56C", danger="#ED8B83",
    ),
    "ambar": _palette(
        bg="#17130D", surface="#211B12", surface_alt="#302719", border="#59462A",
        text="#FFF9ED", muted="#D1C0A1", soft="#EAD9BB", accent="#D68A24",
        accent_hover="#EAA23D", success="#78C992", warning="#F2C65D", danger="#E78378",
    ),
    "vinho": _palette(
        bg="#121113", surface="#1A181C", surface_alt="#252127", border="#453943",
        text="#FAF7FA", muted="#BCB0BB", soft="#DED5DF", accent="#A95870",
        accent_hover="#BD6E85", success="#78C992", warning="#E5BD70", danger="#D77C8E",
    ),
    "machine_red": _palette(
        bg="#090F18", surface="#101722", surface_alt="#172333", border="#344659",
        text="#F4F9FC", muted="#9DB4C0", soft="#DBF6FF", brand="#DBF6FF",
        brand_muted="#9DB4C0", accent="#FF2E3A", accent_hover="#FF5360",
        success="#66D7AD", warning="#F2C15E", danger="#E77C87",
    ),
    "claro": _palette(
        bg="#E9EDF4", surface="#F8F9FC", surface_alt="#FFFFFF", border="#CDD5E3",
        text="#202A3B", muted="#66738A", soft="#46546B", accent="#5D54C7",
        accent_hover="#4E45B7", success="#19885B", warning="#A56A00", danger="#C7465C",
    ),
    "grafite": _palette(
        bg="#111111", surface="#1B1B1D", surface_alt="#29292C", border="#49494F",
        text="#F7F7F8", muted="#BDBDC4", soft="#E1E1E6", accent="#C2C7CF",
        accent_hover="#E0E4EA", success="#83D6A5", warning="#E5C17C", danger="#ED919B",
    ),
}


# Reviewed roles for the original UI literals. Keep the original violet values
# when returning to that theme, including the subtle differences among cards.
_LEGACY_COLOR_GROUPS = {
    "bg": "#080C16",
    "surface": "#101827 #101929",
    "surface_alt": "#162136",
    "surface_deep": "#0A1324 #0B1528 #0C1423 #0D1525",
    "surface_panel": "#101B2E #101C30 #111A2C #111B2D #111C30 #14213A",
    "surface_panel_alt": "#141E32 #17213A #17243A",
    "surface_tile": "#162239",
    "surface_elevated": "#1A2942 #1A2A45 #1B2943 #1C2941",
    "surface_button": "#22324F #253552 #263550 #263653 #263A5B #263B5A #27344D",
    "surface_button_hover": "#34476B #3A4865 #3B4D69 #405B83",
    "surface_action": "#244462 #294660 #304769 #314667",
    "surface_action_hover": "#315A80 #3A6A94",
    "border": "#283750 #283754 #293951 #2D3E5B #30405D #33445F #34445F #344867 #34486C",
    "border_input": "#2A3A58 #4B5E7D #53647F #5C6D91",
    "selection": "#1C2E4B #213251 #354A6E",
    "selection_full": "#314B70",
    "text": "#EEF3FF #F1F5FB #F6F8FF #FFFFFF",
    "text_soft": "#B8C8E8 #BFCDE3 #C9D3FF #CAD6E9 #D8E4FF #E9ECFF",
    "muted": "#687A9A #72809A #8FA1BC #9FB0CC #A9B9D1 #AAB8D4 #AFC2EA",
    "brand": "#D3DCF3", "brand_muted": "#8FA1C9",
    "accent": "#6656D8 #7665E8 #8170E6 #8F7DF0",
    "accent_hover": "#7162DD", "accent_mid": "#9181F0",
    "accent_light": "#9FC7FF #A99AF4 #B7AAFF #B8ACFF #BBAEFF #BFC7FF #C5BDFF #C7BDFF #D8D4FF #DAD3FF #DDD6FF",
    "accent_soft": "#262953 #29254B #342E69 #363768 #3A3379",
    "success": "#55D6A0 #A4EDCE #DDF7EB", "success_hover": "#70E4B4",
    "success_soft": "#17342F #356450",
    "danger": "#F17A91 #F4A7A8 #FFB7AD #E5CFD2", "danger_hover": "#FF92A6",
    "danger_soft": "#291F31 #3A1D2A #3A2637 #3C2A3B #55384E #573248 #72505A",
    "warning": "#F5B942",
}
LEGACY_COLOR_ROLES = {color: role for role, colors in _LEGACY_COLOR_GROUPS.items() for color in colors.split()}


class ThemeColor(str):
    """A color string with a stable role, preserved by CustomTkinter's API."""

    def __new__(cls, role: str, theme: str, original: str | None = None) -> ThemeColor:
        theme = theme if theme in THEMES else DEFAULT_THEME
        original = original or THEMES[DEFAULT_THEME][role]
        value = original if theme == DEFAULT_THEME else THEMES[theme][role]
        result = super().__new__(cls, value)
        result.role = role
        result.original = original
        return result

    def for_theme(self, theme: str) -> ThemeColor:
        return role_color(self.role, theme, self.original)


@lru_cache(maxsize=4096)
def role_color(role: str, theme: str, original: str | None = None) -> ThemeColor:
    return ThemeColor(role, theme, original)


def theme_color(color: object, theme: str) -> object:
    """Resolve a bound role or one of the reviewed original UI literals."""
    if isinstance(color, ThemeColor):
        return color.for_theme(theme)
    if isinstance(color, (tuple, list)):
        converted = [theme_color(item, theme) for item in color]
        return tuple(converted) if isinstance(color, tuple) else converted
    if isinstance(color, str) and color.upper() in LEGACY_COLOR_ROLES:
        original = color.upper()
        return role_color(LEGACY_COLOR_ROLES[original], theme, original)
    return color


def theme_colors(theme: str) -> dict[str, str]:
    """Return Tk-compatible colors carrying their original semantic roles."""
    return {role: role_color(role, theme) for role in THEMES[DEFAULT_THEME]}


def configure_widget_defaults(template: dict, theme: str) -> None:
    """Bind even implicit control colors, including disabled and dropdown states.

    Only update color entries; preserve CustomTkinter's sizes, shapes and fonts.
    Existing widgets keep their own role bindings and are updated separately.
    """
    shared = {"text_color": "text", "text_color_disabled": "muted", "border_color": "border"}
    classes = {
        "CTk": {"fg_color": "surface"}, "CTkToplevel": {"fg_color": "surface"},
        "CTkFrame": {"fg_color": "surface", "top_fg_color": "surface_alt"},
        "CTkButton": {"fg_color": "accent", "hover_color": "accent_hover"},
        "CTkLabel": {},
        "CTkEntry": {"fg_color": "surface_input", "placeholder_text_color": "muted"},
        "CTkCheckBox": {"fg_color": "accent", "hover_color": "accent_hover", "checkmark_color": "accent_text"},
        "CTkSwitch": {"fg_color": "border", "progress_color": "accent", "button_color": "text", "button_hover_color": "text_soft"},
        "CTkRadioButton": {"fg_color": "accent", "hover_color": "accent_hover"},
        "CTkProgressBar": {"fg_color": "surface_button", "progress_color": "accent"},
        "CTkSlider": {"fg_color": "border", "progress_color": "accent", "button_color": "accent", "button_hover_color": "accent_hover"},
        "CTkOptionMenu": {"fg_color": "surface_input", "button_color": "surface_button", "button_hover_color": "surface_button_hover"},
        "CTkComboBox": {"fg_color": "surface_input", "button_color": "surface_button", "button_hover_color": "surface_button_hover"},
        "CTkScrollbar": {"button_color": "border_input", "button_hover_color": "muted"},
        "CTkSegmentedButton": {"fg_color": "surface_button", "selected_color": "accent", "selected_hover_color": "accent_hover", "unselected_color": "surface_button", "unselected_hover_color": "surface_button_hover"},
        "CTkTextbox": {"fg_color": "surface_input", "scrollbar_button_color": "border_input", "scrollbar_button_hover_color": "muted"},
        "CTkScrollableFrame": {"label_fg_color": "surface_panel"},
        "DropdownMenu": {"fg_color": "surface_alt", "hover_color": "selection"},
    }
    for name, roles in classes.items():
        options = template.get(name, {})
        for option, role in {**shared, **roles}.items():
            if option in options:
                options[option] = role_color(role, theme)
