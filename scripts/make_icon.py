from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def make_icon(path: Path) -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = []
    for size in sizes:
        scale = size / 256.0
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=int(44 * scale), fill="#000000")

        diamond = max(2, int(23 * scale))
        centers = [
            (int(128 * scale), int(62 * scale)),
            (int(82 * scale), int(128 * scale)),
            (int(174 * scale), int(128 * scale)),
            (int(128 * scale), int(194 * scale)),
        ]
        for cx, cy in centers:
            draw.polygon(
                [
                    (cx, cy - diamond),
                    (cx + diamond, cy),
                    (cx, cy + diamond),
                    (cx - diamond, cy),
                ],
                fill="#ffffff",
            )
        images.append(image)

    path.parent.mkdir(parents=True, exist_ok=True)
    images[-1].save(path, sizes=[(size, size) for size in sizes])


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    make_icon(root / "assets" / "tarans_renderer_icon.ico")

