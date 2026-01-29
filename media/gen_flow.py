#!/usr/bin/env python3
"""Generate an animated GIF showing the council deliberation data flow."""

from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 860, 480
BG = (13, 17, 23)

# Colors
PURPLE = (136, 127, 255)
PURPLE_DIM = (80, 72, 180)
PURPLE_GLOW = (136, 127, 255, 40)
GREEN = (63, 185, 80)
GREEN_DIM = (40, 120, 55)
ORANGE = (210, 153, 34)
CYAN = (56, 189, 248)
PINK = (219, 112, 170)
TEXT_W = (230, 237, 243)
TEXT_DIM = (125, 133, 144)
BOX_BG = (22, 27, 34)
BOX_BORDER = (48, 54, 61)
DOT_COLOR = (30, 35, 42)

FONT = "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf"

f12 = ImageFont.truetype(FONT, 12)
f13 = ImageFont.truetype(FONT, 13)
f14 = ImageFont.truetype(FONT, 14)
f15 = ImageFont.truetype(FONT, 15)
f16 = ImageFont.truetype(FONT_B, 16)
f18 = ImageFont.truetype(FONT_B, 18)
f11 = ImageFont.truetype(FONT, 11)

AGENT_COLORS = [CYAN, PINK, ORANGE, PURPLE]
AGENT_NAMES = ["Codex", "Gemini", "OpenCode", "ClaudeOR"]
AGENT_X = [100, 285, 470, 655]
AGENT_W = 135
AGENT_H = 42

ROW_Y = [35, 115, 195, 285, 370]


def draw_dots(draw):
    """Subtle dot grid background."""
    for x in range(20, W, 25):
        for y in range(20, H, 25):
            draw.ellipse((x, y, x + 1, y + 1), fill=DOT_COLOR)


def glow_rect(img, xy, color, radius=12, blur=8):
    """Draw a box with outer glow effect."""
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    x1, y1, x2, y2 = xy
    gd.rounded_rectangle(
        (x1 - 4, y1 - 4, x2 + 4, y2 + 4),
        radius=radius + 2,
        fill=(*color[:3], 30),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(blur))
    composite = Image.alpha_composite(img, glow)
    img.paste(composite, (0, 0))


def pill(draw, xy, fill, outline, radius=14):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=2)


def arrow_down(draw, x, y1, y2, color=BOX_BORDER, dashed=False):
    if dashed:
        y = y1
        while y < y2 - 8:
            draw.line([(x, y), (x, min(y + 6, y2 - 8))], fill=color, width=2)
            y += 12
    else:
        draw.line([(x, y1), (x, y2 - 6)], fill=color, width=2)
    draw.polygon([(x - 5, y2 - 8), (x + 5, y2 - 8), (x, y2)], fill=color)


def arrow_right(draw, x1, x2, y, color=BOX_BORDER):
    draw.line([(x1, y), (x2 - 6, y)], fill=color, width=2)
    draw.polygon([(x2 - 8, y - 5), (x2 - 8, y + 5), (x2, y)], fill=color)


def center_text(draw, text, font, x1, x2, y, fill):
    tw = draw.textlength(text, font=font)
    draw.text(((x1 + x2 - tw) / 2, y), text, font=font, fill=fill)


def badge(draw, x, y, text, color):
    """Small colored badge/tag."""
    tw = draw.textlength(text, font=f11)
    pw = tw + 12
    draw.rounded_rectangle((x, y, x + pw, y + 18), radius=9, fill=(*color, ), outline=None)
    draw.text((x + 6, y + 2), text, font=f11, fill=BG)


def new_frame():
    img = Image.new("RGBA", (W, H), (*BG, 255))
    draw = ImageDraw.Draw(img)
    draw_dots(draw)
    return img, draw


def finalize(img):
    return img.convert("RGB")


# ── Step renderers ──────────────────────────────────────────────────

def draw_step_0(img, draw):
    """Entry: council_ask."""
    glow_rect(img, (265, ROW_Y[0], 595, ROW_Y[0] + 52), PURPLE)
    draw = ImageDraw.Draw(img)
    pill(draw, (265, ROW_Y[0], 595, ROW_Y[0] + 52), BOX_BG, PURPLE)
    badge(draw, 275, ROW_Y[0] + 6, "ENTRY", PURPLE)
    draw.text((340, ROW_Y[0] + 5), "council_ask()", font=f18, fill=PURPLE)
    draw.text((310, ROW_Y[0] + 30), "prompt + roles/team + options", font=f13, fill=TEXT_DIM)
    return draw


def draw_step_1(img, draw):
    """Role resolution."""
    draw = draw_step_0(img, draw)
    arrow_down(draw, 430, ROW_Y[0] + 52, ROW_Y[1], PURPLE_DIM)
    pill(draw, (280, ROW_Y[1], 580, ROW_Y[1] + 42), BOX_BG, BOX_BORDER)
    draw.text((310, ROW_Y[1] + 6), "team preset?", font=f14, fill=TEXT_DIM)
    draw.text((420, ROW_Y[1] + 6), "→", font=f14, fill=TEXT_DIM)
    draw.text((440, ROW_Y[1] + 6), "resolve roles", font=f14, fill=TEXT_W)
    draw.text((310, ROW_Y[1] + 24), "inject role prompt per agent", font=f12, fill=TEXT_DIM)
    return draw


def draw_step_2(img, draw):
    """Round 1 agents."""
    draw = draw_step_1(img, draw)
    arrow_down(draw, 430, ROW_Y[1] + 42, ROW_Y[2] - 12, PURPLE_DIM)

    # Round 1 label
    badge(draw, 390, ROW_Y[2] - 12, "ROUND 1", PURPLE)
    draw.text((465, ROW_Y[2] - 11), "parallel dispatch", font=f13, fill=TEXT_DIM)

    # Fan-out lines
    for i, x in enumerate(AGENT_X):
        cx = x + AGENT_W // 2
        draw.line([(430, ROW_Y[2] + 10), (cx, ROW_Y[2] + 22)], fill=AGENT_COLORS[i], width=2)

    # Agent boxes with individual glow
    for i, (name, x) in enumerate(zip(AGENT_NAMES, AGENT_X)):
        c = AGENT_COLORS[i]
        bx = (x, ROW_Y[2] + 22, x + AGENT_W, ROW_Y[2] + 22 + AGENT_H)
        glow_rect(img, bx, c, blur=6)
        draw = ImageDraw.Draw(img)
        pill(draw, bx, BOX_BG, c)
        center_text(draw, name, f16, x, x + AGENT_W, ROW_Y[2] + 32, c)
    return draw


def draw_step_3(img, draw):
    """Results."""
    draw = draw_step_2(img, draw)
    bot = ROW_Y[2] + 22 + AGENT_H
    for i, x in enumerate(AGENT_X):
        cx = x + AGENT_W // 2
        arrow_down(draw, cx, bot, ROW_Y[3], AGENT_COLORS[i], dashed=True)

    pill(draw, (210, ROW_Y[3], 650, ROW_Y[3] + 44), BOX_BG, BOX_BORDER)
    draw.text((230, ROW_Y[3] + 13), "Results:", font=f15, fill=TEXT_W)
    badge(draw, 320, ROW_Y[3] + 13, "success", GREEN)
    draw.text((400, ROW_Y[3] + 13), "+  session IDs", font=f13, fill=TEXT_DIM)
    draw.text((520, ROW_Y[3] + 15), "/", font=f13, fill=TEXT_DIM)
    badge(draw, 540, ROW_Y[3] + 13, "timeout", ORANGE)
    badge(draw, 600, ROW_Y[3] + 13, "error", ORANGE)
    return draw


def draw_step_4(img, draw):
    """Round 2."""
    draw = draw_step_3(img, draw)
    arrow_down(draw, 430, ROW_Y[3] + 44, ROW_Y[4], PURPLE_DIM)

    bx = (180, ROW_Y[4], 620, ROW_Y[4] + 70)
    glow_rect(img, bx, PURPLE, blur=10)
    draw = ImageDraw.Draw(img)
    pill(draw, bx, BOX_BG, PURPLE)
    badge(draw, 195, ROW_Y[4] + 8, "ROUND 2", PURPLE)
    draw.text((280, ROW_Y[4] + 7), "Deliberation", font=f16, fill=PURPLE)
    draw.text((200, ROW_Y[4] + 30), "Agents see all R1 answers → revise positions", font=f15, fill=TEXT_W)
    draw.text((200, ROW_Y[4] + 50), "resume sessions  ·  skip failed agents", font=f13, fill=TEXT_DIM)
    return draw


def draw_step_5(img, draw):
    """Claude synthesis."""
    draw = draw_step_4(img, draw)

    bx = (700, ROW_Y[4] + 8, 810, ROW_Y[4] + 62)
    arrow_right(draw, 620, 700, ROW_Y[4] + 35, GREEN_DIM)
    glow_rect(img, bx, GREEN, blur=8)
    draw = ImageDraw.Draw(img)
    pill(draw, bx, BOX_BG, GREEN)
    badge(draw, 715, ROW_Y[4] + 15, "FINAL", GREEN)
    draw.text((718, ROW_Y[4] + 38), "Claude", font=f16, fill=GREEN)
    return draw


# ── Build frames ────────────────────────────────────────────────────

steps = [draw_step_0, draw_step_1, draw_step_2, draw_step_3, draw_step_4, draw_step_5]

frames = []
durations = []

for si, step_fn in enumerate(steps):
    img, draw = new_frame()
    step_fn(img, draw)
    rgb = finalize(img)
    frames.append(rgb)
    durations.append(5000 if si == len(steps) - 1 else 2500)

out_path = "/home/spok/repos/agentic-mcp-tools/owlex/media/council_flow.gif"

# Use last frame (has all colors) for the shared palette
palette_img = frames[-1].quantize(colors=256, method=Image.Quantize.MEDIANCUT)
quantized = [f.quantize(palette=palette_img, dither=0) for f in frames]

quantized[0].save(
    out_path,
    save_all=True,
    append_images=quantized[1:],
    duration=durations,
    loop=0,
    optimize=False,
)
print(f"Saved {out_path} ({len(quantized)} frames)")
