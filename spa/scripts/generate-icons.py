#!/usr/bin/env python3
"""
Derives the web app's icons and splash image from the source artwork in
`shared/assets/`, so the committed PNGs under `packages/webapp/public/` can
always be regenerated rather than being opaque binaries nobody dares touch.

    cd spa && python3 scripts/generate-icons.py

Needs Pillow (`pip install pillow`). Run it after changing the source artwork;
the outputs are committed, so this is not part of the build.

What each output is for:

`icon-192.png`, `icon-512.png`
    The regular PWA icons: the full artwork, just scaled.

`icon-maskable-512.png`
    Android may crop an icon to a circle, a squircle, or a rounded square of
    its choosing. Only the central 80% ("safe zone") is guaranteed to survive,
    so the artwork is scaled to that and the margin is filled with a colour
    sampled from the source instead of leaving transparent corners.

`favicon.png`, `apple-touch-icon.png`
    Browser tab and iOS home screen. iOS cannot use Web Bluetooth at all (see
    SPA_PLAN.md), but the app still installs and the non-BLE views work.

`splash.webp`
    Shown while the app boots. WebP because this is decorative artwork that
    gets precached by the service worker - a 240 kB JPEG in the offline bundle
    for a screen most users see for 200 ms would be a poor trade.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - developer tooling
    sys.exit("This script needs Pillow: pip install pillow")

SPA_DIR = Path(__file__).resolve().parents[1]
ASSETS = SPA_DIR.parent / "shared" / "assets"
OUTPUT = SPA_DIR / "packages" / "webapp" / "public"

ICON_SOURCE = ASSETS / "hoermoles_ble_icon_abstract_bt.jpeg"
SPLASH_SOURCE = ASSETS / "hoermoles_ble_icon.jpeg"

# Fraction of the maskable icon the artwork may occupy. 0.8 is the safe zone
# the Android adaptive-icon spec guarantees will not be cropped away.
MASKABLE_SAFE_ZONE = 0.8


def background_colour(image: Image.Image) -> tuple[int, int, int]:
    """Average of the four corners - the artwork is framed by sky/background
    there, so this blends the maskable margin into the image rather than
    banding against it."""
    width, height = image.size
    corners = [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)]
    pixels = [image.getpixel(xy) for xy in corners]
    return tuple(sum(channel[i] for channel in pixels) // len(pixels) for i in range(3))  # type: ignore[return-value]


def write_square_icon(source: Image.Image, size: int, target: Path) -> None:
    source.resize((size, size), Image.LANCZOS).save(target, "PNG", optimize=True)
    print(f"wrote {target.relative_to(SPA_DIR)} ({target.stat().st_size:,} bytes)")


def write_maskable_icon(source: Image.Image, size: int, target: Path) -> None:
    inner = int(size * MASKABLE_SAFE_ZONE)
    canvas = Image.new("RGB", (size, size), background_colour(source))
    canvas.paste(
        source.resize((inner, inner), Image.LANCZOS),
        ((size - inner) // 2, (size - inner) // 2),
    )
    canvas.save(target, "PNG", optimize=True)
    print(f"wrote {target.relative_to(SPA_DIR)} ({target.stat().st_size:,} bytes)")


def main() -> int:
    for path in (ICON_SOURCE, SPLASH_SOURCE):
        if not path.exists():
            sys.exit(f"Missing source artwork: {path}")

    OUTPUT.mkdir(parents=True, exist_ok=True)

    icon = Image.open(ICON_SOURCE).convert("RGB")
    write_square_icon(icon, 192, OUTPUT / "icon-192.png")
    write_square_icon(icon, 512, OUTPUT / "icon-512.png")
    write_square_icon(icon, 180, OUTPUT / "apple-touch-icon.png")
    write_square_icon(icon, 64, OUTPUT / "favicon.png")
    write_maskable_icon(icon, 512, OUTPUT / "icon-maskable-512.png")

    splash = Image.open(SPLASH_SOURCE).convert("RGB")
    splash_target = OUTPUT / "splash.webp"
    splash.resize((512, 512), Image.LANCZOS).save(
        splash_target, "WEBP", quality=82, method=6
    )
    print(
        f"wrote {splash_target.relative_to(SPA_DIR)} ({splash_target.stat().st_size:,} bytes)"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
