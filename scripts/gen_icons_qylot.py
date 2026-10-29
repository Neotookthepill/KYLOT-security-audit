#!/usr/bin/env python3
"""iter186 — Génère toutes les icônes QYLOT (favicon, apple-touch, PWA logos)
à partir du logo Q officiel : tuile arrondie sombre + anneau argenté + queue
métallique diagonale.

Utilise uniquement Pillow (dépendance déjà présente).
"""
from PIL import Image, ImageDraw
from pathlib import Path

OUT_DIR = Path("/app/frontend/public")

# Palette exacte du logo (mêmes valeurs que le SVG côté SplashScreen / Login)
BG_TOP = (17, 19, 24, 255)     # #111318
BG_BOTTOM = (5, 7, 15, 255)    # #05070f
RING = (226, 232, 240, 255)    # #E2E8F0 (silver / slate-200)
TAIL = (100, 116, 139, 255)    # #64748B (slate-500 — queue métallique)


def make_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Rayon corners = 22% (correspond au rx=112 sur viewBox 512 du SVG)
    r = int(size * 0.22)

    # Fond dégradé vertical (top plus clair, bottom plus profond)
    # → simulé en 2 rectangles arrondis empilés avec un dégradé linéaire manuel
    grad = Image.new("RGBA", (size, size), BG_TOP)
    for y in range(size):
        t = y / max(1, size - 1)
        r_c = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g_c = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b_c = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        ImageDraw.Draw(grad).line([(0, y), (size, y)], fill=(r_c, g_c, b_c, 255))

    # Masque de la tuile arrondie
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)

    # Géométrie du Q — dérivée du SVG (viewBox 0..512, cx=256 cy=256 r=150, stroke=30)
    cx = cy = size / 2
    # Rayon extérieur du cercle du Q — proportionnel à 150/512
    outer_r = size * (150 / 512)
    ring_w = max(1, int(round(size * (30 / 512))))
    # Cercle stroke (anneau argenté) — ellipse d'épaisseur ring_w
    d.ellipse(
        [cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r],
        outline=RING, width=ring_w,
    )

    # Queue diagonale métallique — from (280,280) to (436,436) sur 512, épaisseur 36
    x1 = size * (280 / 512); y1 = size * (280 / 512)
    x2 = size * (436 / 512); y2 = size * (436 / 512)
    tail_w = max(2, int(round(size * (36 / 512))))
    d.line([(x1, y1), (x2, y2)], fill=TAIL, width=tail_w)

    return img


def save_png(size: int, name: str):
    out = OUT_DIR / name
    make_icon(size).save(out, format="PNG", optimize=True)
    print(f"→ {name} ({size}px, {out.stat().st_size} bytes)")


def save_ico():
    # favicon.ico multi-sizes (Windows / older browsers)
    sizes = [16, 24, 32, 48, 64]
    imgs = [make_icon(s) for s in sizes]
    out = OUT_DIR / "favicon.ico"
    imgs[0].save(out, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"→ favicon.ico multi-size, {out.stat().st_size} bytes")


def save_svg():
    # SVG « source » — utilisé par kylot-icon.svg (référencé partout)
    svg = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 512 512'>
  <defs>
    <linearGradient id='bg' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0%' stop-color='#111318'/>
      <stop offset='100%' stop-color='#05070f'/>
    </linearGradient>
    <linearGradient id='ring' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0%' stop-color='#F8FAFC'/>
      <stop offset='55%' stop-color='#CBD5E1'/>
      <stop offset='100%' stop-color='#64748B'/>
    </linearGradient>
    <linearGradient id='tail' x1='0' y1='0' x2='1' y2='1'>
      <stop offset='0%' stop-color='#94A3B8'/>
      <stop offset='60%' stop-color='#475569'/>
      <stop offset='100%' stop-color='#1E293B'/>
    </linearGradient>
  </defs>
  <rect width='512' height='512' rx='112' fill='url(#bg)'/>
  <circle cx='256' cy='256' r='150' fill='none' stroke='url(#ring)' stroke-width='30'/>
  <line x1='280' y1='280' x2='436' y2='436' stroke='url(#tail)' stroke-width='36' stroke-linecap='butt'/>
</svg>
"""
    out = OUT_DIR / "kylot-icon.svg"
    out.write_text(svg, encoding="utf-8")
    print(f"→ kylot-icon.svg refreshed, {out.stat().st_size} bytes")


if __name__ == "__main__":
    save_png(16, "favicon-16.png")
    save_png(32, "favicon-32.png")
    save_png(180, "apple-touch-icon.png")
    save_png(192, "logo192.png")
    save_png(512, "logo512.png")
    save_ico()
    save_svg()
    print("Done.")
