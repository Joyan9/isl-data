from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size: int):
    candidates = [
        Path(__file__).parent / "static" / "fonts" / "Inter-Regular.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def make_share_card(path: Path, item: dict, verdict: str) -> None:
    image = Image.new("RGB", (1200, 630), "#111827")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1200, 14), fill=item["bundle"].home_color)
    draw.rectangle((600, 0, 1200, 14), fill=item["bundle"].away_color)
    draw.text((70, 65), "GIVE INDIAN FOOTBALL A CHANCE", fill="#b9c2d0", font=_font(25))
    draw.text((70, 155), item["bundle"].home_name, fill="#f3f4f6", font=_font(42))
    draw.text((70, 235), item["bundle"].away_name, fill="#f3f4f6", font=_font(42))
    draw.text((840, 155), f'{item["bundle"].score("home")} – {item["bundle"].score("away")}', fill="#f3f4f6", font=_font(72))
    draw.text((70, 390), f'xG  {item["home_xg"] or "—"} – {item["away_xg"] or "—"}', fill="#7dd3fc", font=_font(40))
    draw.rounded_rectangle((70, 490, 520, 565), radius=18, fill="#172033", outline="#3b4a61", width=2)
    draw.text((95, 508), f"Fair result?  {verdict}", fill="#f3f4f6", font=_font(27))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", optimize=True)
