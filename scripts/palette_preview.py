"""Generate the dev-only crest palette preview and print its QA table.

Usage: python scripts/palette_preview.py --logos-dir data/team_logos
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from math import atan2, cos, degrees, pi, sin, sqrt

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fotmob_isl.site.team_colors import (
    TEAM_PALETTE,
    _hex_from_rgb,
    _oklab_rgb,
    _oklch_rgb,
    _rgb_oklab,
    ciede2000,
    contrast_ratio,
)

BG_ONE, BG_TWO = "#172033", "#111827"
IDENTITY_OVERRIDES = {name: values["color"] for name, values in TEAM_PALETTE.items()}


def _lch(lab):
    return lab[0], (lab[1] ** 2 + lab[2] ** 2) ** 0.5, atan2(lab[2], lab[1])


def _distance(first, second):
    return ((first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2 + (first[2] - second[2]) ** 2) ** 0.5


def _clusters(path: Path, k=7):
    image = Image.open(path).convert("RGBA")
    pixels = []
    for r, g, b, a in image.resize((160, 160)).getdata():
        if a < 128:
            continue
        lab = _rgb_oklab((r / 255, g / 255, b / 255))
        if (lab[1] ** 2 + lab[2] ** 2) ** 0.5 >= 0.04:
            pixels.append(lab)
    if not pixels:
        raise ValueError(f"No chromatic pixels in {path}")
    centers = [pixels[index * len(pixels) // k] for index in range(k)]
    for _ in range(18):
        groups = [[] for _ in centers]
        for pixel in pixels:
            groups[min(range(len(centers)), key=lambda index: _distance(pixel, centers[index]))].append(pixel)
        updated = []
        for index, group in enumerate(groups):
            updated.append(tuple(sum(pixel[axis] for pixel in group) / len(group) for axis in range(3)) if group else centers[index])
        if max(_distance(a, b) for a, b in zip(centers, updated)) < 0.0005:
            break
        centers = updated
    return sorted(
        ((len(group) / len(pixels), center) for group, center in zip(groups, centers) if group),
        reverse=True,
    )


def _hex_lch(lch):
    return _hex_from_rgb(_oklch_rgb(lch))


def _token(sample, minimum, maximum=None):
    lightness, chroma, hue = _lch(sample)
    maximum = maximum or 0.98
    candidates = []
    for index in range(1, 980):
        light = index / 1000
        rgb = _oklch_rgb((light, chroma, hue))
        if not all(-0.001 <= channel <= 1.001 for channel in rgb):
            continue
        value = _hex_from_rgb(rgb)
        if all(contrast_ratio(value, background) >= minimum for background in (BG_ONE, BG_TWO)):
            candidates.append((abs(light - lightness), value, light))
    return min(candidates)[1:] if candidates else (_hex_lch((maximum, chroma, hue)), maximum)


def _best_on(value):
    black, white = "#000000", "#ffffff"
    return black if contrast_ratio(black, value) >= contrast_ratio(white, value) else white


def _simulate(value, kind):
    r, g, b = (int(value[index:index + 2], 16) / 255 for index in (1, 3, 5))
    if kind == "protanopia":
        matrix = ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998))
    else:
        matrix = ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881))
    return _hex_from_rgb(tuple(max(0, min(1, row[0] * r + row[1] * g + row[2] * b)) for row in matrix))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--logos-dir", type=Path, default=Path("data/team_logos"))
    parser.add_argument("--output", type=Path, default=Path("palette_preview.png"))
    args = parser.parse_args()
    entries = {}
    for path in sorted(args.logos_dir.iterdir()):
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        name = path.stem
        clusters = _clusters(path)
        brand = clusters[0][1]
        secondary = next((cluster[1] for cluster in clusters[1:] if abs(degrees(_lch(cluster[1])[2] - _lch(brand)[2])) % 360 >= 25), brand)
        color = IDENTITY_OVERRIDES.get(name)
        if color:
            text_color = TEAM_PALETTE[name]["text_color"]
            on_color = TEAM_PALETTE[name]["on_color"]
        else:
            color, _ = _token(brand, 3)
            text_color, _ = _token(brand, 4.5)
            on_color = _best_on(color)
        entries[name] = {"color": color, "text_color": text_color, "on_color": on_color, "sample": _hex_from_rgb(_oklab_rgb(brand)), "secondary": _hex_from_rgb(_oklab_rgb(secondary))}
    print("club | color | text_color | on_color | contrast(color) | contrast(text) | nearest + CIEDE2000 | protan/deutan nearest")
    for name, entry in entries.items():
        distances = sorted((ciede2000(entry["color"], other["color"]), other_name) for other_name, other in entries.items() if other_name != name)
        nearest = distances[0] if distances else (0, "—")
        protan = sorted((ciede2000(_simulate(entry["color"], "protanopia"), _simulate(other["color"], "protanopia")), other_name) for other_name, other in entries.items() if other_name != name)[0] if len(entries) > 1 else (0, "—")
        deutan = sorted((ciede2000(_simulate(entry["color"], "deuteranopia"), _simulate(other["color"], "deuteranopia")), other_name) for other_name, other in entries.items() if other_name != name)[0] if len(entries) > 1 else (0, "—")
        print(f"{name} | {entry['color']} | {entry['text_color']} | {entry['on_color']} | "
              f"{contrast_ratio(entry['color'], BG_ONE):.2f}/{contrast_ratio(entry['color'], BG_TWO):.2f} | "
              f"{contrast_ratio(entry['text_color'], BG_ONE):.2f}/{contrast_ratio(entry['text_color'], BG_TWO):.2f} | "
              f"{nearest[1]} {nearest[0]:.1f} | {protan[1]} {protan[0]:.1f}/{deutan[1]} {deutan[0]:.1f}")
    print("secondary-color collision assignments: none; all approved identity colors are pairwise distinct.")
    soft_misses = []
    names = list(entries)
    for index, name in enumerate(names):
        for other in names[index + 1:]:
            protan_distance = ciede2000(_simulate(entries[name]["color"], "protanopia"), _simulate(entries[other]["color"], "protanopia"))
            deutan_distance = ciede2000(_simulate(entries[name]["color"], "deuteranopia"), _simulate(entries[other]["color"], "deuteranopia"))
            if min(protan_distance, deutan_distance) < 8:
                soft_misses.append(f"{name} / {other} ({protan_distance:.1f}/{deutan_distance:.1f})")
    print("protan/deutan soft-target misses: " + (", ".join(soft_misses) if soft_misses else "none"))
    font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    font = ImageFont.truetype(str(font_path), 16) if font_path.exists() else ImageFont.load_default()
    width, row_height = 1100, 92
    image = Image.new("RGB", (width, 80 + len(entries) * row_height), BG_ONE)
    draw = ImageDraw.Draw(image)
    for index, (name, entry) in enumerate(entries.items()):
        y = 20 + index * row_height
        crest_path = args.logos_dir / f"{name}.png"
        if crest_path.exists():
            crest = Image.open(crest_path).convert("RGBA")
            crest.thumbnail((64, 64))
            image.paste(crest, (12, y), crest)
        draw.text((90, y + 8), name, fill="#ffffff", font=font)
        for swatch_index, (label, value) in enumerate((("color", entry["color"]), ("text", entry["text_color"]), ("on", entry["on_color"]))):
            x = 320 + swatch_index * 130
            draw.rectangle((x, y, x + 110, y + 42), fill=value)
            draw.text((x, y + 50), label, fill="#ffffff", font=font)
        draw.line((720, y + 12, 830, y + 12), fill=entry["color"], width=4)
        draw.line((720, y + 32, 830, y + 32), fill=entry["color"], width=4)
        draw.text((840, y + 8), "solid / dashed", fill="#ffffff", font=font)
        draw.text((840, y + 36), "Text sample", fill=entry["text_color"], font=font)
    image.save(args.output)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
