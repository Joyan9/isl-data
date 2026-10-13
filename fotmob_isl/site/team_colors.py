"""Crest-derived, high-contrast team colour tokens.

The checked-in palette is generated from ``data/team_logos`` with the
development helper ``scripts/palette_preview.py``. Runtime code intentionally
has no image-processing dependency or filesystem lookup.
"""
from __future__ import annotations

from math import atan2, cos, degrees, exp, hypot, isfinite, pi, sin, sqrt
from pathlib import Path
from typing import Iterable


TEAM_PALETTE = {
    "Bengaluru FC": {"color": "#97b886", "text_color": "#62944d", "on_color": "#000000"},
    "Chennaiyin FC": {"color": "#e413ff", "text_color": "#d930ff", "on_color": "#000000"},
    "Churchill Brothers": {"color": "#fb5a0a", "text_color": "#ff3715", "on_color": "#000000"},
    "East Bengal FC": {"color": "#07a4ff", "text_color": "#2884ff", "on_color": "#000000"},
    "FC Goa": {"color": "#f9e3f1", "text_color": "#9f7d92", "on_color": "#000000"},
    "Inter Kashi": {"color": "#feba24", "text_color": "#e16c00", "on_color": "#000000"},
    "Kerala Blasters FC": {"color": "#39f7ff", "text_color": "#00c6d6", "on_color": "#000000"},
    "Mohun Bagan SG": {"color": "#b07a85", "text_color": "#ca6a7a", "on_color": "#000000"},
    "Mumbai City FC": {"color": "#dafc0b", "text_color": "#aff300", "on_color": "#000000"},
    "Northeast United FC": {"color": "#0d9a9b", "text_color": "#179697", "on_color": "#000000"},
    "Odisha FC": {"color": "#b1a1f6", "text_color": "#8672ff", "on_color": "#000000"},
    "Punjab FC": {"color": "#968907", "text_color": "#9b8617", "on_color": "#000000"},
    "SC Delhi": {"color": "#fefde2", "text_color": "#8a8963", "on_color": "#000000"},
}

TEAM_COLORS = {name: values["color"] for name, values in TEAM_PALETTE.items()}


def _require(name: str) -> dict[str, str]:
    try:
        return TEAM_PALETTE[name]
    except KeyError as exc:
        raise KeyError(f"Unknown club palette: {name}") from exc


def colors_for(home: str, away: str) -> tuple[str, str]:
    """Return the primary tokens for two known clubs."""
    return _require(home)["color"], _require(away)["color"]


def color_for(name: str) -> dict[str, str]:
    return _require(name)


# The following helpers are used by the dev-only preview/generator. Keeping
# the conversions here makes the checked-in values reproducible and testable.
def _srgb(value: int) -> float:
    value /= 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _hex_rgb(value: str) -> tuple[float, float, float]:
    return tuple(int(value[index:index + 2], 16) / 255 for index in (1, 3, 5))


def _rgb_oklab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (_srgb(round(value * 255)) for value in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = (value ** (1 / 3) if value > 0 else 0 for value in (l, m, s))
    return (
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    )


def _oklab_rgb(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    l, a, b = lab
    l_, m_, s_ = (
        l + 0.3963377774 * a + 0.2158037573 * b,
        l - 0.1055613458 * a - 0.0638541728 * b,
        l - 0.0894841775 * a - 1.2914855480 * b,
    )
    l_, m_, s_ = l_ ** 3, m_ ** 3, s_ ** 3
    return (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )


def _oklch_rgb(lch: tuple[float, float, float]) -> tuple[float, float, float]:
    lightness, chroma, hue = lch
    return _oklab_rgb((lightness, chroma * cos(hue), chroma * sin(hue)))


def _hex_from_rgb(rgb: tuple[float, float, float]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(value * 255))) for value in rgb))


def _relative_luminance(value: str) -> float:
    r, g, b = _hex_rgb(value)
    return 0.2126 * _srgb(round(r * 255)) + 0.7152 * _srgb(round(g * 255)) + 0.0722 * _srgb(round(b * 255))


def contrast_ratio(first: str, second: str) -> float:
    light, dark = sorted((_relative_luminance(first), _relative_luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _ciede2000(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    # Sharma et al. CIEDE2000, with OKLab converted to an Lab-like scale.
    l1, a1, b1 = first[0] * 100, first[1] * 100, first[2] * 100
    l2, a2, b2 = second[0] * 100, second[1] * 100, second[2] * 100
    c1, c2 = hypot(a1, b1), hypot(a2, b2)
    mean_c = (c1 + c2) / 2
    g = 0.5 * (1 - sqrt(mean_c ** 7 / (mean_c ** 7 + 25 ** 7))) if mean_c else 0
    ap1, ap2 = (1 + g) * a1, (1 + g) * a2
    cp1, cp2 = hypot(ap1, b1), hypot(ap2, b2)
    hp1, hp2 = (degrees(atan2(b, a)) % 360 for a, b in ((ap1, b1), (ap2, b2)))
    dl, dc = l2 - l1, cp2 - cp1
    dh = hp2 - hp1
    if cp1 * cp2 == 0:
        dh = 0
    elif dh > 180:
        dh -= 360
    elif dh < -180:
        dh += 360
    dtheta = 30 * exp(-(((((hp1 + hp2) / 2) - 275) / 25) ** 2))
    rc = 2 * sqrt(cp1 * cp2 ** 0 + 1)  # preserves a finite weighting for near-grey samples
    rc = 2 * sqrt((cp1 * cp2) ** 7 / ((cp1 * cp2) ** 7 + 25 ** 7)) if cp1 * cp2 else 0
    mean_lp = (l1 + l2) / 2
    mean_cp = (cp1 + cp2) / 2
    hp = (hp1 + hp2 + 360) / 2 if abs(hp1 - hp2) <= 180 else (hp1 + hp2 + 720) / 2
    sl = 1 + 0.015 * (mean_lp - 50) ** 2 / sqrt(20 + (mean_lp - 50) ** 2)
    sc, sh = 1 + 0.045 * mean_cp, 1 + 0.015 * mean_cp * (1 - 0.17 * cos(pi * (hp - 30) / 180))
    rt = -sin(2 * dtheta * pi / 180) * rc
    return sqrt((dl / sl) ** 2 + (dc / sc) ** 2 + (2 * sqrt(cp1 * cp2) * sin(dh * pi / 360) / sh) ** 2 + rt * (dc / sc) * (2 * sqrt(cp1 * cp2) * sin(dh * pi / 360) / sh))


def ciede2000(first: str, second: str) -> float:
    def lab(value: str) -> tuple[float, float, float]:
        r, g, b = _hex_rgb(value)
        r, g, b = (_srgb(round(channel * 255)) for channel in (r, g, b))
        x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
        y = (r * 0.2126 + g * 0.7152 + b * 0.0722) / 1.00000
        z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883
        def pivot(channel: float) -> float:
            return channel ** (1 / 3) if channel > 0.008856 else 7.787 * channel + 16 / 116
        x, y, z = pivot(x), pivot(y), pivot(z)
        return 116 * y - 16, 500 * (x - y), 200 * (y - z)
    return _ciede2000(lab(first), lab(second))


def palette_entries() -> Iterable[tuple[str, dict[str, str]]]:
    return TEAM_PALETTE.items()
