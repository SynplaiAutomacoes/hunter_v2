from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass(frozen=True, slots=True)
class ResolvedTermColors:
    primary: str
    accent: str
    text: str
    muted: str
    on_primary: str
    on_accent: str


def _normalize_hex(color: str, *, fallback: str) -> str:
    normalized = str(color or "").strip()
    if _HEX_COLOR_RE.match(normalized):
        return normalized.upper()
    return fallback.upper()


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _relative_luminance(color: str) -> float:
    r, g, b = _hex_to_rgb(color)
    channels = []
    for channel in (r, g, b):
        normalized = channel / 255.0
        channels.append(normalized / 12.92 if normalized <= 0.03928 else ((normalized + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast_ratio(foreground: str, background: str) -> float:
    l1 = _relative_luminance(foreground)
    l2 = _relative_luminance(background)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _pick_on_color(background: str) -> str:
    white_ratio = _contrast_ratio("#FFFFFF", background)
    black_ratio = _contrast_ratio("#000000", background)
    return "#FFFFFF" if white_ratio >= black_ratio else "#000000"


def resolve_term_colors(
    *,
    primary: str,
    accent: str,
    text: str,
    muted: str,
) -> ResolvedTermColors:
    resolved_primary = _normalize_hex(primary, fallback="#000000")
    resolved_accent = _normalize_hex(accent, fallback="#DC2626")
    resolved_text = _normalize_hex(text, fallback="#111827")
    resolved_muted = _normalize_hex(muted, fallback="#6B7280")

    if _contrast_ratio(resolved_text, "#FFFFFF") < 4.5:
        resolved_text = "#111827"

    return ResolvedTermColors(
        primary=resolved_primary,
        accent=resolved_accent,
        text=resolved_text,
        muted=resolved_muted,
        on_primary=_pick_on_color(resolved_primary),
        on_accent=_pick_on_color(resolved_accent),
    )


def validate_term_colors(colors: ResolvedTermColors) -> list[str]:
    errors: list[str] = []
    if _contrast_ratio(colors.text, "#FFFFFF") < 4.5:
        errors.append("A cor do texto precisa ter contraste suficiente com o fundo branco.")
    if _contrast_ratio(colors.on_primary, colors.primary) < 4.5:
        errors.append("A cor principal precisa de contraste adequado para títulos.")
    if _contrast_ratio(colors.on_accent, colors.accent) < 4.5:
        errors.append("A cor de destaque precisa de contraste adequado.")
    return errors


def colors_to_context(colors: ResolvedTermColors) -> dict[str, str]:
    return {
        "primary": colors.primary,
        "accent": colors.accent,
        "text": colors.text,
        "muted": colors.muted,
        "on_primary": colors.on_primary,
        "on_accent": colors.on_accent,
    }


def extract_sections_from_content(content: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not content:
        return []
    sections = content.get("sections")
    if isinstance(sections, list):
        return [section for section in sections if isinstance(section, dict)]
    return []
