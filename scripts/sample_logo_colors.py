"""One-off developer utility; requires Pillow locally, not at runtime."""
from pathlib import Path

from PIL import Image


for path in sorted(Path("data/team_logos").glob("*")):
    with Image.open(path).convert("RGB") as image:
        colors = image.resize((64, 64)).getcolors(64 * 64) or []
        color = max(colors, key=lambda item: item[0])[1]
        print(f"{path.stem!r}: '#{color[0]:02x}{color[1]:02x}{color[2]:02x}',")
