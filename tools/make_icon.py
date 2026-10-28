"""Draws the integration icon: python tools/make_icon.py (needs Pillow)."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 2048  # drawn 4x, scaled down for anti-aliasing
OUT = Path(__file__).resolve().parent.parent / "custom_components/xmeye/brand"


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def icon() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # background: rounded square, vertical gradient
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    top, bottom = (37, 99, 235), (12, 18, 40)
    for y in range(S):
        gd.line([(0, y), (S, y)], fill=lerp(top, bottom, y / S) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)

    cx, cy = S // 2, int(S * 0.44)
    # soft shadow under the lens
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse(
        [cx - 620, cy - 560, cx + 620, cy + 680], fill=(0, 0, 0, 110)
    )
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(60)))
    d = ImageDraw.Draw(img)

    def circle(r, fill, dx=0, dy=0):
        d.ellipse([cx + dx - r, cy + dy - r, cx + dx + r, cy + dy + r], fill=fill)

    circle(600, (236, 241, 250, 255))  # housing
    circle(500, (15, 23, 42, 255))  # bezel
    # lens glass gradient
    for r in range(420, 0, -6):
        circle(r, lerp((14, 165, 233), (30, 58, 138), 1 - r / 420) + (255,))
    circle(200, (8, 13, 28, 255))  # pupil
    circle(95, (255, 255, 255, 230), dx=-170, dy=-170)  # highlight
    circle(40, (255, 255, 255, 160), dx=150, dy=150)

    # recording dot
    rx, ry, rr = int(S * 0.80), int(S * 0.17), 120
    d.ellipse([rx - rr - 22, ry - rr - 22, rx + rr + 22, ry + rr + 22], fill=(12, 18, 40, 255))
    d.ellipse([rx - rr, ry - rr, rx + rr, ry + rr], fill=(239, 68, 68, 255))

    # timeline with recorded segments
    y0, y1 = int(S * 0.80), int(S * 0.86)
    x0, x1 = int(S * 0.16), int(S * 0.84)
    d.rounded_rectangle([x0, y0, x1, y1], radius=(y1 - y0) // 2, fill=(255, 255, 255, 60))
    w = x1 - x0
    for a, b, color in (
        (0.02, 0.30, (148, 163, 184, 255)),
        (0.36, 0.52, (96, 165, 250, 255)),
        (0.56, 0.80, (148, 163, 184, 255)),
        (0.84, 0.98, (96, 165, 250, 255)),
    ):
        d.rounded_rectangle(
            [x0 + int(w * a), y0 + 18, x0 + int(w * b), y1 - 18], radius=(y1 - y0) // 2, fill=color
        )
    return img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    big = icon()
    for name, size in (("icon.png", 256), ("icon@2x.png", 512)):
        big.resize((size, size), Image.LANCZOS).save(OUT / name, optimize=True)
    print("written to", OUT)
