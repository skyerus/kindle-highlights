import os
import sys
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

# Kindle Paperwhite 2 portrait resolution
WIDTH, HEIGHT = 758, 1024
MARGIN = 40
QUOTE_AREA_HEIGHT = int(HEIGHT * 0.82)
FONT_SIZES = [36, 32, 28, 24, 20, 18, 16]
FOOTER_SIZE = 18
COVER_WIDTH = 70
COVER_TEXT_GAP = 16
DEFAULT_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"


def _font_path() -> str:
    return os.environ.get("QUOTE_FONT_PATH", DEFAULT_FONT_PATH)


def _wrap_to_width(text: str, font, max_width: int, draw) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        cur = ""
        for w in words:
            trial = (cur + " " + w).strip()
            bbox = draw.textbbox((0, 0), trial, font=font)
            if bbox[2] - bbox[0] <= max_width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
    return lines


def _fetch_cover(url):
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return Image.open(BytesIO(resp.content)).convert("L")
    except Exception as e:
        print(f"Cover fetch failed for {url}: {e}", file=sys.stderr)
        return None


def render_quote_to_png(quote: dict, output_path: Path) -> None:
    img = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw = ImageDraw.Draw(img)
    text = f'“{quote["highlight"]}”'
    max_text_width = WIDTH - 2 * MARGIN
    available_height = QUOTE_AREA_HEIGHT - 2 * MARGIN

    chosen_font = None
    chosen_lines: list[str] = []
    for size in FONT_SIZES:
        font = ImageFont.truetype(_font_path(), size=size)
        lines = _wrap_to_width(text, font, max_text_width, draw)
        line_h = int(size * 1.4)
        if line_h * len(lines) <= available_height:
            chosen_font = font
            chosen_lines = lines
            break

    if chosen_font is None:
        chosen_font = ImageFont.truetype(_font_path(), size=FONT_SIZES[-1])
        chosen_lines = _wrap_to_width(text, chosen_font, max_text_width, draw)
        line_h = int(FONT_SIZES[-1] * 1.4)
        max_lines = available_height // line_h
        if len(chosen_lines) > max_lines:
            chosen_lines = chosen_lines[:max_lines]
            chosen_lines[-1] = chosen_lines[-1].rstrip(".,;:!? ") + "…"

    line_h = int(chosen_font.size * 1.4)
    block_h = line_h * len(chosen_lines)
    y = MARGIN + (available_height - block_h) // 2
    for line in chosen_lines:
        bbox = draw.textbbox((0, 0), line, font=chosen_font)
        x = (WIDTH - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=chosen_font, fill=0)
        y += line_h

    cover = _fetch_cover(quote.get("cover_url"))
    has_cover = cover is not None
    if has_cover:
        cover_h = int(cover.height * (COVER_WIDTH / cover.width))
        cover = cover.resize((COVER_WIDTH, cover_h), Image.LANCZOS)
        cover_x = MARGIN
        cover_y = HEIGHT - MARGIN - cover_h
        img.paste(cover, (cover_x, cover_y))
        footer_text_x_left = cover_x + COVER_WIDTH + COVER_TEXT_GAP
        footer_max_width = WIDTH - MARGIN - footer_text_x_left
    else:
        footer_text_x_left = MARGIN
        footer_max_width = WIDTH - 2 * MARGIN

    footer_font = ImageFont.truetype(_font_path(), size=FOOTER_SIZE)
    footer_text = f'— {quote["book_title"]}, {quote["author"]}'
    footer_lines = _wrap_to_width(footer_text, footer_font, footer_max_width, draw)
    footer_line_h = int(FOOTER_SIZE * 1.3)
    fy = HEIGHT - MARGIN - footer_line_h * len(footer_lines)
    for line in footer_lines:
        bbox = draw.textbbox((0, 0), line, font=footer_font)
        line_w = bbox[2] - bbox[0]
        x = footer_text_x_left if has_cover else WIDTH - MARGIN - line_w
        draw.text((x, fy), line, font=footer_font, fill=0)
        fy += footer_line_h

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG", optimize=True)
