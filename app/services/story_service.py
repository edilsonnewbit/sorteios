"""Geração de imagem Story Instagram — design premium 1080×1920."""
import io
import os
import logging
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("Pillow não disponível — story generation desativado")

W, H = 1080, 1920

# ── Font discovery ────────────────────────────────────────────────────────────
_FONT_PATHS = [
    # Open Sans (instalado via apt)
    "/usr/share/fonts/truetype/open-sans/OpenSans-ExtraBold.ttf",
    "/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
_FONT_PATHS_REGULAR = [
    "/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _find_font(paths: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _load_image(url_or_path: str) -> Optional[Image.Image]:
    try:
        if url_or_path.startswith("http"):
            req = urllib.request.Request(url_or_path, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                return Image.open(io.BytesIO(r.read())).convert("RGBA")
        else:
            # Strip leading slash and try both relative and /data paths
            path = url_or_path.lstrip("/")
            candidates = [
                path,
                os.path.join("/data", path.replace("static/", "", 1)),
                os.path.join("/data/uploads", os.path.basename(path)),
            ]
            for p in candidates:
                if os.path.exists(p):
                    return Image.open(p).convert("RGBA")
    except Exception as e:
        logger.debug("Story: erro ao carregar imagem: %s", e)
    return None


def _rounded_image(img: Image.Image, radius: int) -> Image.Image:
    """Aplica cantos arredondados via máscara alpha."""
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, img.width, img.height], radius=radius, fill=255)
    result = Image.new("RGBA", img.size, (0, 0, 0, 0))
    result.paste(img, mask=mask)
    return result


def _draw_gradient_rect(draw: ImageDraw.ImageDraw, xy: tuple,
                        color_top: tuple, color_bottom: tuple, radius: int = 0):
    x0, y0, x1, y1 = xy
    ht = y1 - y0
    for i in range(ht):
        t = i / ht
        r = int(color_top[0] + (color_bottom[0] - color_top[0]) * t)
        g = int(color_top[1] + (color_bottom[1] - color_top[1]) * t)
        b = int(color_top[2] + (color_bottom[2] - color_top[2]) * t)
        a = int(color_top[3] + (color_bottom[3] - color_top[3]) * t) if len(color_top) == 4 else 255
        draw.line([(x0, y0 + i), (x1, y0 + i)], fill=(r, g, b, a))


def _paste_rgba(base: Image.Image, layer: Image.Image, pos: tuple):
    """Paste RGBA layer respecting alpha."""
    base.paste(layer, pos, mask=layer.split()[3])


def generate_story(
    raffle_title: str,
    prize_description: str,
    price_per_quota: float,
    total: int,
    sold: int,
    share_url: str,
    prize_image_url: Optional[str] = None,
    qr_code_base64: Optional[str] = None,
) -> bytes | None:
    if not PIL_AVAILABLE:
        return None

    # ── Fonts ──────────────────────────────────────────────────────────────────
    f_title  = _find_font(_FONT_PATHS, 96)
    f_title2 = _find_font(_FONT_PATHS, 80)
    f_big    = _find_font(_FONT_PATHS, 68)
    f_med    = _find_font(_FONT_PATHS, 48)
    f_sm     = _find_font(_FONT_PATHS_REGULAR, 38)
    f_xs     = _find_font(_FONT_PATHS_REGULAR, 30)
    f_tag    = _find_font(_FONT_PATHS, 28)

    # ── Canvas ─────────────────────────────────────────────────────────────────
    canvas = Image.new("RGBA", (W, H), (5, 10, 28, 255))

    # ── Background: blurred prize image ────────────────────────────────────────
    prize_img = _load_image(prize_image_url) if prize_image_url else None

    if prize_img:
        bg = prize_img.convert("RGB").resize((W, H), Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(38))
        # Desaturate slightly
        from PIL import ImageEnhance
        bg = ImageEnhance.Color(bg).enhance(0.5)
        bg = bg.convert("RGBA")
        # Dark overlay gradient
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for y in range(H):
            t = y / H
            # Denser at bottom
            alpha = int(140 + 100 * t)
            od.line([(0, y), (W, y)], fill=(5, 10, 28, min(alpha, 240)))
        canvas = Image.alpha_composite(bg, overlay)
    else:
        # Fallback: animated gradient background
        d_bg = ImageDraw.Draw(canvas)
        for y in range(H):
            t = y / H
            r = int(5 + 15 * t)
            g = int(10 + 10 * t)
            b = int(28 + 40 * t)
            d_bg.line([(0, y), (W, y)], fill=(r, g, b, 255))

    draw = ImageDraw.Draw(canvas, "RGBA")

    # ── Decorative elements: floating orbs ────────────────────────────────────
    # Purple orb top-right
    orb1 = Image.new("RGBA", (500, 500), (0, 0, 0, 0))
    od1 = ImageDraw.Draw(orb1)
    for i in range(250, 0, -1):
        alpha = int(55 * (i / 250))
        od1.ellipse([250 - i, 250 - i, 250 + i, 250 + i], fill=(124, 58, 237, alpha))
    canvas.paste(orb1, (700, -100), orb1)

    # Cyan orb bottom-left
    orb2 = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    od2 = ImageDraw.Draw(orb2)
    for i in range(200, 0, -1):
        alpha = int(40 * (i / 200))
        od2.ellipse([200 - i, 200 - i, 200 + i, 200 + i], fill=(6, 182, 212, alpha))
    canvas.paste(orb2, (-80, H - 350), orb2)

    draw = ImageDraw.Draw(canvas, "RGBA")

    # ── Top brand tag ──────────────────────────────────────────────────────────
    tag_text = "🎟  SORTEIO OFICIAL"
    tag_w = 340
    draw.rounded_rectangle([(W - tag_w) // 2, 60, (W + tag_w) // 2, 120],
                            radius=30, fill=(124, 58, 237, 200),
                            outline=(167, 139, 250, 180), width=1)
    draw.text((W // 2, 90), tag_text, font=f_tag, fill=(220, 210, 255, 255), anchor="mm")

    # ── Prize image card (the hero) ────────────────────────────────────────────
    card_w, card_h = 880, 660
    card_x = (W - card_w) // 2
    card_y = 160

    if prize_img:
        # Glow behind card (layered ellipses)
        glow = Image.new("RGBA", (card_w + 100, card_h + 100), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        for i in range(40, 0, -1):
            alpha = int(120 * (i / 40))
            gd.rounded_rectangle([40 - i, 40 - i, card_w + 60 + i, card_h + 60 + i],
                                  radius=36 + i, fill=(124, 58, 237, alpha))
        canvas.paste(glow, (card_x - 50, card_y - 50), glow)

        # Second glow: cyan
        glow2 = Image.new("RGBA", (card_w + 80, card_h + 80), (0, 0, 0, 0))
        gd2 = ImageDraw.Draw(glow2)
        for i in range(25, 0, -1):
            alpha = int(70 * (i / 25))
            gd2.rounded_rectangle([40 - i, 40 - i, card_w + 40 + i, card_h + 40 + i],
                                   radius=30 + i, fill=(6, 182, 212, alpha))
        canvas.paste(glow2, (card_x - 40, card_y - 40), glow2)

        # Actual prize image
        card_img = prize_img.convert("RGBA").resize((card_w, card_h), Image.LANCZOS)
        card_img = _rounded_image(card_img, 28)
        _paste_rgba(canvas, card_img, (card_x, card_y))

        # Inner border
        border_layer = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        bd = ImageDraw.Draw(border_layer)
        bd.rounded_rectangle([0, 0, card_w - 1, card_h - 1], radius=28,
                              outline=(255, 255, 255, 45), width=2)
        _paste_rgba(canvas, border_layer, (card_x, card_y))

        # Bottom fade on card
        fade = Image.new("RGBA", (card_w, 180), (0, 0, 0, 0))
        fd = ImageDraw.Draw(fade)
        for i in range(180):
            a = int(200 * (i / 180))
            fd.line([(0, i), (card_w, i)], fill=(5, 10, 28, a))
        _paste_rgba(canvas, fade, (card_x, card_y + card_h - 180))
    else:
        # No image: frosted placeholder
        draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h],
                               radius=28, fill=(20, 30, 60, 180),
                               outline=(124, 58, 237, 100), width=2)
        draw.text((W // 2, card_y + card_h // 2), "🎁", font=f_big, anchor="mm",
                  fill=(167, 139, 250, 200))

    # ── Title area ─────────────────────────────────────────────────────────────
    title_y = card_y + card_h + 40

    # Word-wrap title
    max_w = W - 120
    words = raffle_title.upper().split()
    lines, line = [], ""
    font_title = f_title if len(raffle_title) < 20 else f_title2
    for word in words:
        test = f"{line} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font_title)
        if bbox[2] - bbox[0] > max_w and line:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)

    for i, ln in enumerate(lines[:3]):
        y = title_y + i * (font_title.size + 8)
        # Text shadow
        draw.text((W // 2 + 2, y + 2), ln, font=font_title,
                  fill=(0, 0, 0, 120), anchor="mm")
        draw.text((W // 2, y), ln, font=font_title, fill="#ffffff", anchor="mm")

    title_bottom = title_y + len(lines[:3]) * (font_title.size + 8)

    # Description
    if prize_description:
        desc = prize_description[:70] + ("…" if len(prize_description) > 70 else "")
        draw.text((W // 2, title_bottom + 16), desc, font=f_sm,
                  fill=(154, 164, 178, 230), anchor="mm")
        title_bottom += f_sm.size + 24

    # ── Price card (frosted glass) ─────────────────────────────────────────────
    price_y = title_bottom + 36
    price_h = 140

    # Glass background
    glass = Image.new("RGBA", (W - 120, price_h), (0, 0, 0, 0))
    gld = ImageDraw.Draw(glass)
    gld.rounded_rectangle([0, 0, W - 121, price_h - 1], radius=22,
                           fill=(255, 255, 255, 18),
                           outline=(255, 255, 255, 40), width=1)
    _paste_rgba(canvas, glass, (60, price_y))

    draw.text((W // 2, price_y + 32), "APENAS", font=f_tag,
              fill=(196, 181, 253, 220), anchor="mm")
    price_text = f"R$ {price_per_quota:.2f}  por número"
    draw.text((W // 2, price_y + 95), price_text, font=f_big,
              fill="#ffffff", anchor="mm")

    # ── Progress bar ───────────────────────────────────────────────────────────
    bar_y = price_y + price_h + 44
    bar_x, bar_w_total, bar_h = 80, W - 160, 22
    pct = min(sold / total, 1.0) if total > 0 else 0

    # Track
    draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w_total, bar_y + bar_h],
                           radius=11, fill=(255, 255, 255, 25))
    # Fill
    if pct > 0:
        fill_w = max(int(bar_w_total * pct), bar_h)
        fill_layer = Image.new("RGBA", (fill_w, bar_h), (0, 0, 0, 0))
        for x in range(fill_w):
            t = x / fill_w
            r = int(124 + (6 - 124) * t)
            g = int(58 + (182 - 58) * t)
            b = int(237 + (212 - 237) * t)
            ImageDraw.Draw(fill_layer).line([(x, 0), (x, bar_h)], fill=(r, g, b, 255))
        fill_layer = _rounded_image(fill_layer, 11)
        _paste_rgba(canvas, fill_layer, (bar_x, bar_y))

    pct_text = f"{pct*100:.0f}% concluído  •  {max(0, 100 - (pct*100)):.0f}% para concluir"
    draw.text((W // 2, bar_y + bar_h + 22), pct_text, font=f_xs,
              fill=(154, 164, 178, 200), anchor="mm")

    # Urgency badge
    urg_y = bar_y + bar_h + 68
    if pct >= 0.9 and pct < 1:
        draw.rounded_rectangle([(W - 500) // 2, urg_y, (W + 500) // 2, urg_y + 60],
                               radius=16, fill=(245, 158, 11, 40),
                               outline=(245, 158, 11, 120), width=1)
        draw.text((W // 2, urg_y + 30), f"⚡ Reta final: {pct*100:.0f}% da meta atingida!",
                  font=f_xs, fill=(251, 191, 36, 255), anchor="mm")
    elif pct > 0.5:
        draw.rounded_rectangle([(W - 480) // 2, urg_y, (W + 480) // 2, urg_y + 60],
                               radius=16, fill=(239, 68, 68, 35),
                               outline=(248, 113, 113, 100), width=1)
        draw.text((W // 2, urg_y + 30), f"🔥 {pct*100:.0f}% da meta já foi atingida!",
                  font=f_xs, fill=(252, 165, 165, 255), anchor="mm")

    # ── URL call-to-action ─────────────────────────────────────────────────────
    url_display = share_url.replace("https://", "").replace("http://", "")[:50]
    # Label
    draw.text((W // 2, H - 170), "Acesse agora e garanta o seu número:", font=f_xs,
              fill=(154, 164, 178, 200), anchor="mm")
    # URL destacada
    draw.text((W // 2, H - 120), url_display, font=f_sm,
              fill=(103, 232, 249, 230), anchor="mm")

    # Bottom gradient bar
    bar_layer = Image.new("RGBA", (W, 12), (0, 0, 0, 0))
    for x in range(W):
        t = x / W
        r = int(124 + (6 - 124) * t)
        g = int(58 + (182 - 58) * t)
        b = int(237 + (212 - 237) * t)
        ImageDraw.Draw(bar_layer).line([(x, 0), (x, 12)], fill=(r, g, b, 255))
    _paste_rgba(canvas, bar_layer, (0, H - 12))

    # ── Export ─────────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()
