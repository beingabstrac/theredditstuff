#!/usr/bin/env python3
import json
import asyncio
import math
import os
import shutil
import sys
import subprocess
import tempfile
import textwrap
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEPS = ROOT / ".deps"
OUT = ROOT / "outputs"
VIDEO_OUT = OUT / "theredditstuff_mvp.mp4"
STORY_OUT = OUT / "theredditstuff_storyboard.json"
ICON_DIR = ROOT / "assets" / "icons"

W, H = 1080, 1920
BG_FRAMES = 48
BG_FPS = 24
BRAND_GAP = 34
BRAND_SPACE = 96

DEFAULT_SUBREDDITS = [
    "AskReddit",
    "hypotheticalsituation",
    "WouldYouRather",
    "NoStupidQuestions",
    "TooAfraidToAsk",
    "DoesAnybodyElse",
    "unpopularopinion",
]


SAMPLE_POST = {
    "subreddit": "AskReddit",
    "author": "ordinary_opinion",
    "score": 48200,
    "num_comments": 9300,
    "title": "What is socially acceptable but actually rude?",
    "body": "",
    "comments": [
        {
            "author": "speakerphone_truth",
            "score": 21400,
            "body": "Putting someone on speakerphone without telling the other people in the room. It instantly changes the whole conversation.",
        },
        {
            "author": "early_is_rude",
            "score": 18900,
            "body": "Showing up way too early to someone's house. Five minutes is fine. Thirty minutes early is just a surprise inspection.",
        },
        {
            "author": "dont_ask_that",
            "score": 15100,
            "body": "Asking couples when they are having kids. People treat it like small talk, but it can be a really loaded question.",
        },
        {
            "author": "public_not_content",
            "score": 12700,
            "body": "Recording strangers in public for content. Everyone acts like it is normal now, but most people did not agree to be part of your video.",
        },
    ],
}

KOKORO_PIPELINE = None
KOKORO_VOICES = ["af_heart", "am_adam", "af_bella", "am_michael"]
EDGE_VOICES = [
    "en-US-AndrewMultilingualNeural",
    "en-US-AvaMultilingualNeural",
    "en-US-BrianMultilingualNeural",
    "en-US-EmmaMultilingualNeural",
]

UNSAFE_TERMS = [
    "nsfw",
    "porn",
    "nude",
    "nudes",
    "sex",
    "sexual",
    "onlyfans",
    "rape",
    "raped",
    "suicide",
    "self harm",
    "murder",
    "kill myself",
    "child abuse",
    "child abse",
    "underage",
    "minor",
    "minors",
    "molest",
    "grooming",
    "pedophile",
    "politic",
    "trump",
    "biden",
    "election",
    "democrat",
    "republican",
    "liberal",
    "conservative",
    "israel",
    "palestine",
    "ukraine",
    "russia",
    "war",
    "religion",
]


def is_safe_text(*parts):
    text = " ".join(part or "" for part in parts).lower()
    return not any(term in text for term in UNSAFE_TERMS)


def reddit_request(path, token):
    req = urllib.request.Request(
        f"https://oauth.reddit.com{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "reddit-reel-mvp/0.1 by local-codex",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def reddit_public_request(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 theredditstuff/0.1",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def reddit_token():
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
    password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    password_mgr.add_password(None, "https://www.reddit.com/api/v1/access_token", client_id, client_secret)
    opener = urllib.request.build_opener(urllib.request.HTTPBasicAuthHandler(password_mgr))
    req = urllib.request.Request(
        "https://www.reddit.com/api/v1/access_token",
        data=body,
        headers={"User-Agent": "reddit-reel-mvp/0.1 by local-codex"},
    )
    with opener.open(req, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["access_token"]


def subreddit_pool():
    raw = os.getenv("SUBREDDITS", "")
    if not raw.strip():
        return DEFAULT_SUBREDDITS
    return [item.strip().strip("/").removeprefix("r/") for item in raw.split(",") if item.strip()]


def fetch_subreddit_candidates(token, subreddit):
    try:
        if token:
            listing = reddit_request(f"/r/{subreddit}/top?t=day&limit=20", token)
        else:
            listing = reddit_public_request(
                f"https://www.reddit.com/r/{subreddit}/top.json?t=day&limit=20&raw_json=1"
            )
    except Exception as exc:
        print(f"Skipping r/{subreddit}: {exc}")
        return []

    candidates = []
    for child in listing["data"]["children"]:
        data = child["data"]
        if data.get("stickied") or data.get("over_18"):
            continue
        if not is_safe_text(data.get("title", ""), data.get("selftext", "")):
            continue
        if data.get("num_comments", 0) < 20:
            continue
        candidates.append(data)
    return candidates


def fetch_reddit_post():
    token = reddit_token()

    candidates = []
    for subreddit in subreddit_pool():
        candidates.extend(fetch_subreddit_candidates(token, subreddit))
    if not candidates:
        return SAMPLE_POST

    picked = max(candidates, key=shareable_score)

    try:
        if token:
            comments_data = reddit_request(f"/comments/{picked['id']}?limit=40&sort=top", token)
        else:
            comments_data = reddit_public_request(
                f"https://www.reddit.com/comments/{picked['id']}.json?limit=40&sort=top&raw_json=1"
            )
    except Exception as exc:
        print(f"Falling back to sample comments: {exc}")
        comments_data = [None, {"data": {"children": []}}]

    comments = []
    for child in comments_data[1]["data"]["children"]:
        if child.get("kind") != "t1":
            continue
        data = child["data"]
        body = data.get("body", "")
        if body in {"[deleted]", "[removed]"} or len(body) < 35:
            continue
        if not is_safe_text(body, data.get("author", "")):
            continue
        comments.append(
            {
                "author": data.get("author", "redditor"),
                "score": data.get("score", 0),
                "body": body,
            }
        )

    return {
        "subreddit": picked.get("subreddit", "AskReddit"),
        "author": picked.get("author", "redditor"),
        "score": picked.get("score", 0),
        "num_comments": picked.get("num_comments", 0),
        "title": picked["title"],
        "body": picked.get("selftext", ""),
        "comments": comments[:4],
        "source_url": f"https://www.reddit.com{picked['permalink']}",
    }


def shareable_score(post):
    title = post.get("title", "").lower()
    words = title.split()
    score = 0

    relatable = [
        "relationship",
        "friend",
        "family",
        "work",
        "school",
        "money",
        "dating",
        "social",
        "people",
        "parents",
        "kids",
        "roommate",
        "coworker",
        "partner",
        "strangers",
    ]
    debatable = [
        "acceptable",
        "rude",
        "wrong",
        "overrated",
        "red flag",
        "unpopular",
        "shouldn't",
        "pretend",
        "normalize",
        "attractive",
        "unattractive",
        "rather",
        "would you",
        "hypothetical",
        "annoying",
        "fair",
        "unfair",
    ]
    unsafe = ["politic", "religion", "war", "suicide", "murder", "abuse", "rape", "death", "nsfw"]

    score += sum(10 for word in relatable if word in title)
    score += sum(16 for word in debatable if word in title)
    score += min(post.get("num_comments", 0) / 150, 25)
    score += min(post.get("score", 0) / 2000, 20)
    if post.get("subreddit") in DEFAULT_SUBREDDITS[:3]:
        score += 8

    if 6 <= len(words) <= 18:
        score += 18
    if len(title) > 135:
        score -= 30
    if any(word in title for word in unsafe):
        score -= 100

    return score


def font(size, bold=False):
    candidates = [
        "/Library/Fonts/SF-Pro-Text-Bold.otf" if bold else "/Library/Fonts/SF-Pro-Text-Regular.otf",
        "/Library/Fonts/SF-Pro-Display-Bold.otf" if bold else "/Library/Fonts/SF-Pro-Display-Regular.otf",
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def wrap(draw, text, max_width, font_obj):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textbbox((0, 0), trial, font=font_obj)[2] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_multiline(draw, text, xy, max_width, font_obj, fill, line_gap=18, max_lines=14):
    x, y = xy
    lines = wrap(draw, text, max_width, font_obj)
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [lines[max_lines - 1].rstrip(".") + "..."]
    for line in lines:
        draw.text((x, y), line, font=font_obj, fill=fill)
        y += font_obj.size + line_gap
    return y


def rounded_rect(draw, xy, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def compact_number(value):
    value = int(value or 0)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


@lru_cache(maxsize=8)
def icon_mask(name, size):
    icon = Image.open(ICON_DIR / f"{name}.png").convert("RGBA")
    pixels = icon.load()
    xs, ys = [], []
    for py in range(icon.height):
        for px in range(icon.width):
            r, g, b, _ = pixels[px, py]
            if not (r > 245 and g > 245 and b > 245):
                xs.append(px)
                ys.append(py)
    if xs:
        icon = icon.crop((min(xs), min(ys), max(xs) + 1, max(ys) + 1))

    raw_mask = Image.new("L", icon.size, 0)
    mask_pixels = raw_mask.load()
    icon_pixels = icon.load()
    for py in range(icon.height):
        for px in range(icon.width):
            r, g, b, _ = icon_pixels[px, py]
            mask_pixels[px, py] = 0 if r > 245 and g > 245 and b > 245 else 255

    raw_mask.thumbnail((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    mask.paste(raw_mask, ((size - raw_mask.width) // 2, (size - raw_mask.height) // 2))
    return mask


def draw_svg_icon(draw, name, x, y, size, color):
    draw.bitmap((x, y), icon_mask(name, size), fill=color)


def draw_metric_chip(draw, x, y, icon_name, value):
    chip_h = 48
    icon = 19
    gap = 12
    left_pad = 18
    right_pad = 22
    text_font = font(27, True)
    text = compact_number(value)
    bbox = draw.textbbox((0, 0), text, font=text_font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    chip_w = max(116, left_pad + icon + gap + text_w + right_pad)
    rounded_rect(draw, (x, y, x + chip_w, y + chip_h), chip_h // 2, "#eef1f3")
    icon_y = y + (chip_h - icon) // 2
    text_x = x + left_pad + icon + gap
    text_y = y + (chip_h - text_h) // 2 - bbox[1] - 1
    draw_svg_icon(draw, icon_name, x + left_pad, icon_y, icon, "#3f454b")
    draw.text((text_x, text_y), text, font=text_font, fill="#2f353b")
    return x + chip_w + 14


def draw_vote_group(draw, x, y, score):
    return draw_metric_chip(draw, x, y, "reddit-upvote", score)


def draw_comment_button(draw, x, y, comments):
    return draw_metric_chip(draw, x, y, "reddit-comment", comments)


def draw_action_row(draw, x, y, score, comments=None):
    next_x = draw_vote_group(draw, x, y, score)
    if comments is not None:
        draw_comment_button(draw, next_x, y, comments)


def draw_brand_below_card(draw, y2):
    brand = "@theredditstuff"
    brand_font = font(42, True)
    bbox = draw.textbbox((0, 0), brand, font=brand_font)
    draw.text(((W - (bbox[2] - bbox[0])) / 2, y2 + BRAND_GAP), brand, font=brand_font, fill=(255, 255, 255, 128))


def card_bounds(content_h, min_h=430):
    height = max(min_h, min(content_h, 940))
    y1 = (H - height - BRAND_SPACE) // 2
    return 64, y1, W - 64, y1 + height


def draw_post_component(draw, segment):
    pad = 50
    title_font = font(54, False)
    body_font = font(39, False)
    meta_font = font(30, True)
    weak_font = font(28, False)

    max_width = W - 64 * 2 - pad * 2
    title_lines = wrap(draw, segment["text"], max_width, title_font)[:7]
    body = segment.get("body", "").strip()
    body_lines = wrap(draw, body, max_width, body_font)[:4] if body else []
    content_h = 60 + 58 + len(title_lines) * (title_font.size + 17) + 104 + 60
    if body_lines:
        content_h += 18 + len(body_lines) * (body_font.size + 12)

    x1, y1, x2, y2 = card_bounds(content_h)
    rounded_rect(draw, (x1, y1, x2, y2), 28, "#ffffff")
    x = x1 + pad
    y = y1 + 48

    draw.text((x, y), f"r/{segment.get('subreddit', 'AskReddit')}", font=meta_font, fill="#1a1a1b")
    draw.text((x, y + 36), f"u/{segment.get('author', 'redditor')}", font=weak_font, fill="#57606a")

    y += 102
    for line in title_lines:
        draw.text((x, y), line, font=title_font, fill="#111111")
        y += title_font.size + 17

    if body_lines:
        y += 16
        for line in body_lines:
            draw.text((x, y), line, font=body_font, fill="#222222")
            y += body_font.size + 12

    draw_action_row(draw, x, y2 - 104, segment.get("score", 0), segment.get("num_comments", 0))
    draw_brand_below_card(draw, y2)


def draw_comment_component(draw, segment):
    pad = 50
    body_font = font(54, False)
    author_font = font(31, True)
    weak_font = font(28, False)
    max_width = W - 64 * 2 - pad * 2
    body_lines = wrap(draw, segment["text"], max_width, body_font)[:9]
    content_h = 60 + 55 + len(body_lines) * (body_font.size + 17) + 104 + 60

    x1, y1, x2, y2 = card_bounds(content_h)
    rounded_rect(draw, (x1, y1, x2, y2), 28, "#ffffff")
    x = x1 + pad
    y = y1 + 48

    draw.text((x, y), f"u/{segment.get('author', 'redditor')}", font=author_font, fill="#1a1a1b")
    draw.text((x, y + 36), segment.get("intro", "says"), font=weak_font, fill="#57606a")

    y += 100
    for line in body_lines:
        draw.text((x, y), line, font=body_font, fill="#111111")
        y += body_font.size + 17

    draw_action_row(draw, x, y2 - 104, segment.get("score", 0))
    draw_brand_below_card(draw, y2)


def draw_cta_component(draw, segment):
    text_font = font(54, False)
    lines = segment["text"].split("\n")
    line_h = text_font.size + 17
    block_h = len(lines) * line_h - 17
    content_h = block_h + 150
    x1, y1, x2, y2 = card_bounds(content_h, min_h=300)
    rounded_rect(draw, (x1, y1, x2, y2), 28, "#ffffff")
    y = y1 + ((y2 - y1) - block_h) // 2
    for line in lines:
        draw.text((x1 + 50, y), line, font=text_font, fill="#111111")
        y += line_h
    draw_brand_below_card(draw, y2)


BG_PALETTES = [
    ((8, 13, 18), (18, 58, 72), (57, 42, 91), (13, 82, 64)),
    ((10, 12, 24), (30, 52, 108), (20, 88, 82), (80, 48, 84)),
    ((14, 14, 17), (74, 54, 38), (82, 36, 58), (28, 60, 76)),
    ((7, 14, 22), (24, 82, 56), (50, 48, 100), (16, 64, 92)),
    ((16, 12, 22), (76, 38, 82), (32, 72, 90), (86, 64, 30)),
]


def reel_seed(post):
    raw = f"{post.get('subreddit', '')}:{post.get('author', '')}:{post.get('title', '')}"
    return sum((i + 1) * ord(ch) for i, ch in enumerate(raw))


def shader_background(seed, phase):
    small_w, small_h = 144, 256
    palette = BG_PALETTES[seed % len(BG_PALETTES)]
    img = Image.new("RGB", (small_w, small_h))
    pixels = img.load()
    t = phase * math.tau
    centers = [
        (0.22 + 0.05 * math.cos(t + seed * 0.013), 0.24 + 0.06 * math.sin(t * 0.9)),
        (0.78 + 0.06 * math.cos(t * 0.7 + 1.8), 0.30 + 0.05 * math.sin(t + seed * 0.021)),
        (0.36 + 0.05 * math.sin(t * 0.8 + 2.4), 0.74 + 0.06 * math.cos(t * 0.6)),
        (0.72 + 0.04 * math.sin(t * 0.6 + 4.0), 0.82 + 0.05 * math.cos(t * 0.8 + 1.3)),
    ]
    for y in range(small_h):
        ny = y / (small_h - 1)
        for x in range(small_w):
            nx = x / (small_w - 1)
            weights = []
            for cx, cy in centers:
                dist = (nx - cx) ** 2 + (ny - cy) ** 2
                weights.append(math.exp(-dist * 7.5))
            base_weight = 1.15
            total = base_weight + sum(weights)
            r = palette[0][0] * base_weight
            g = palette[0][1] * base_weight
            b = palette[0][2] * base_weight
            for weight, color in zip(weights, palette[1:]):
                r += color[0] * weight
                g += color[1] * weight
                b += color[2] * weight
            vignette = 0.68 + 0.32 * (1 - min(1, ((nx - 0.5) ** 2 + (ny - 0.5) ** 2) * 2.0))
            pixels[x, y] = (int((r / total) * vignette), int((g / total) * vignette), int((b / total) * vignette))
    return img.resize((W, H), Image.Resampling.BICUBIC)


def make_card(segment, index, total, bg_seed, phase=0):
    img = shader_background(bg_seed, phase)
    draw = ImageDraw.Draw(img, "RGBA")

    kind = segment.get("kind", "post")
    if kind == "comment":
        draw_comment_component(draw, segment)
    elif kind == "cta":
        draw_cta_component(draw, segment)
    else:
        draw_post_component(draw, segment)
    return img


def run_ffmpeg(args):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def make_voice(text, audio_path, index):
    if edge_voice(text, audio_path, index):
        return
    if kokoro_voice(text, audio_path, index):
        return

    tts = shutil.which("espeak-ng")
    if not tts:
        raise RuntimeError("No local TTS found. Install edge-tts or espeak-ng.")
    voice = "en-us+m3" if index % 2 else "en-us+f3"
    subprocess.run([tts, "-v", voice, "-s", "155", "-w", str(audio_path), text], check=True)


def edge_voice(text, audio_path, index):
    if not DEPS.exists():
        return False

    try:
        sys.path.insert(0, str(DEPS))
        import edge_tts

        voice = EDGE_VOICES[index % len(EDGE_VOICES)]

        async def synthesize():
            communicate = edge_tts.Communicate(text, voice=voice, rate="+16%", pitch="+0Hz")
            await communicate.save(str(audio_path))

        asyncio.run(synthesize())
        return audio_path.exists() and audio_path.stat().st_size > 0
    except Exception as exc:
        print(f"edge-tts failed, falling back: {exc}")
        return False


def kokoro_voice(text, audio_path, index):
    global KOKORO_PIPELINE
    if os.getenv("USE_KOKORO") != "1":
        return False

    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline

        if KOKORO_PIPELINE is None:
            KOKORO_PIPELINE = KPipeline(lang_code="a")

        voice = KOKORO_VOICES[index % len(KOKORO_VOICES)]
        chunks = []
        for _, _, audio in KOKORO_PIPELINE(text, voice=voice):
            chunks.append(audio)
        sf.write(audio_path, np.concatenate(chunks), 24000)
        return True
    except Exception as exc:
        print(f"Kokoro failed, falling back to espeak-ng: {exc}")
        return False


def audio_duration(audio_path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            str(audio_path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return float(result.stdout.strip())


def segment_to_video(frame_pattern, audio_path, video_path, duration):
    run_ffmpeg(
        [
            "-stream_loop",
            "-1",
            "-framerate",
            str(BG_FPS),
            "-i",
            str(frame_pattern),
            "-t",
            f"{duration:.2f}",
            "-i",
            str(audio_path),
            "-vf",
            "format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-r",
            "24",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            str(video_path),
        ]
    )


def render_segment_frames(segment, index, total, frames_dir, bg_seed):
    frames_dir.mkdir(parents=True, exist_ok=True)
    for frame in range(BG_FRAMES):
        phase = frame / BG_FRAMES
        make_card(segment, index, total, bg_seed, phase).save(frames_dir / f"frame_{frame:03}.png")


CTA_OPTIONS = [
    ("rude", "Is this rude or normal?\nComment your take."),
    ("wrong", "Who is in the wrong here?\nComment below."),
    ("red flag", "Is this a red flag?\nComment yes or no."),
    ("overrated", "Agree or disagree?\nComment below."),
    ("unpopular", "Hot take or bad take?\nComment below."),
    ("dating", "Would you stay or leave?\nComment below."),
    ("relationship", "Whose side are you on?\nComment below."),
    ("friend", "Would you say something?\nComment below."),
    ("work", "Would you report this or ignore it?\nComment below."),
]


def cta_for_title(title):
    lower = title.lower()
    for keyword, cta in CTA_OPTIONS:
        if keyword in lower:
            return cta
    return "What would you do?\nComment below."


def spoken_username(username):
    return (username or "someone").replace("_", " ").replace("-", " ")


def comment_voice_intro(body, index):
    lower = body.lower()
    if any(word in lower for word in ["i think", "i believe", "imo", "in my opinion"]):
        return "thinks"
    if any(word in lower for word in ["i feel", "feels", "felt"]):
        return "feels"
    if any(word in lower for word in ["people", "everyone", "someone", "nobody"]):
        return "points out"
    return ["says", "thinks", "points out", "brings up"][index % 4]


def build_segments(post):
    title = post["title"].strip()
    subreddit = post.get("subreddit", "AskReddit")
    post_author = post.get("author", "redditor")
    segments = [
        {
            "kind": "post",
            "label": "Post",
            "text": title,
            "body": " ".join(post.get("body", "").split()),
            "author": post_author,
            "subreddit": subreddit,
            "score": post.get("score", 0),
            "num_comments": post.get("num_comments", len(post.get("comments", []))),
            "voice": f"In {subreddit}, {spoken_username(post_author)} asked: {title}",
        }
    ]
    for i, comment in enumerate(post["comments"][:4], start=1):
        body = " ".join(comment["body"].split())
        body = textwrap.shorten(body, width=230, placeholder="...")
        author = comment.get("author", "redditor")
        intro = comment_voice_intro(body, i)
        segments.append(
            {
                "kind": "comment",
                "label": f"Top reply {i}",
                "text": body,
                "author": author,
                "intro": intro,
                "score": comment.get("score", 0),
                "voice": f"{spoken_username(author)} {intro}: {body}",
            }
        )

    cta = cta_for_title(title)
    segments.append(
        {
            "kind": "cta",
            "label": "CTA",
            "text": cta,
            "voice": cta.replace("\n", " "),
        }
    )
    return segments


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    post = fetch_reddit_post()
    bg_seed = reel_seed(post)
    segments = build_segments(post)
    STORY_OUT.write_text(json.dumps({"post": post, "background_seed": bg_seed, "segments": segments}, indent=2), encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="theredditstuff_") as tmp:
        work = Path(tmp)
        part_paths = []
        for index, segment in enumerate(segments):
            frames_dir = work / f"segment_{index:02}_frames"
            audio_path = work / f"segment_{index:02}.wav"
            video_path = work / f"segment_{index:02}.mp4"

            render_segment_frames(segment, index, len(segments), frames_dir, bg_seed)
            make_voice(segment["voice"], audio_path, index)
            duration = audio_duration(audio_path) + 0.15
            segment_to_video(frames_dir / "frame_%03d.png", audio_path, video_path, duration)
            part_paths.append(video_path)

        concat_file = work / "concat.txt"
        concat_file.write_text("".join(f"file '{path}'\n" for path in part_paths), encoding="utf-8")
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(VIDEO_OUT)])

    print(VIDEO_OUT)
    print(STORY_OUT)


if __name__ == "__main__":
    main()
