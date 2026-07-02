#!/usr/bin/env python3
import json
import asyncio
import os
import shutil
import sys
import subprocess
import tempfile
import textwrap
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEPS = ROOT / ".deps"
OUT = ROOT / "outputs"
VIDEO_OUT = OUT / "theredditstuff_mvp.mp4"
STORY_OUT = OUT / "theredditstuff_storyboard.json"

W, H = 1080, 1920


SAMPLE_POST = {
    "subreddit": "AskReddit",
    "author": "ordinary_opinion",
    "score": 48200,
    "num_comments": 9300,
    "title": "What is socially acceptable but actually rude?",
    "body": "",
    "comments": [
        {
            "author": "user_1",
            "score": 21400,
            "body": "Putting someone on speakerphone without telling the other people in the room. It instantly changes the whole conversation.",
        },
        {
            "author": "user_2",
            "score": 18900,
            "body": "Showing up way too early to someone's house. Five minutes is fine. Thirty minutes early is just a surprise inspection.",
        },
        {
            "author": "user_3",
            "score": 15100,
            "body": "Asking couples when they are having kids. People treat it like small talk, but it can be a really loaded question.",
        },
        {
            "author": "user_4",
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


def fetch_askreddit_post():
    token = reddit_token()
    if not token:
        return SAMPLE_POST

    listing = reddit_request("/r/top?t=day&limit=25", token)
    posts = listing["data"]["children"]
    candidates = [
        child["data"]
        for child in posts
        if not child["data"].get("stickied") and not child["data"].get("over_18")
    ]
    picked = max(candidates, key=shareable_score)

    comments_data = reddit_request(f"/comments/{picked['id']}?limit=40&sort=top", token)
    comments = []
    for child in comments_data[1]["data"]["children"]:
        if child.get("kind") != "t1":
            continue
        data = child["data"]
        body = data.get("body", "")
        if body in {"[deleted]", "[removed]"} or len(body) < 35:
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
    ]
    unsafe = ["politic", "religion", "war", "suicide", "murder", "abuse", "rape", "death"]

    score += sum(10 for word in relatable if word in title)
    score += sum(16 for word in debatable if word in title)
    score += min(post.get("num_comments", 0) / 150, 25)
    score += min(post.get("score", 0) / 2000, 20)

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


def draw_upvote_icon(draw, x, y, size, color):
    scale = size / 20
    points = [
        (10, 2.2),
        (17.0, 9.2),
        (12.2, 9.2),
        (12.2, 15.0),
        (11.8, 16.3),
        (10.8, 17.1),
        (9.8, 17.2),
        (8.7, 16.9),
        (7.8, 15.9),
        (7.8, 9.2),
        (3.0, 9.2),
    ]
    xy = [(x + px * scale, y + py * scale) for px, py in points]
    draw.line(xy + [xy[0]], fill=color, width=max(2, int(size * 0.12)), joint="curve")


def draw_comment_icon(draw, x, y, size, color):
    width = max(2, int(size * 0.11))
    draw.ellipse((x + size * 0.08, y + size * 0.08, x + size * 0.92, y + size * 0.82), outline=color, width=width)
    tail = [
        (x + size * 0.30, y + size * 0.76),
        (x + size * 0.16, y + size * 0.96),
        (x + size * 0.50, y + size * 0.80),
    ]
    draw.line(tail, fill=color, width=width, joint="curve")


def draw_vote_group(draw, x, y, score):
    chip_h = 54
    icon = 22
    text_font = font(28, True)
    text = compact_number(score)
    text_w = draw.textbbox((0, 0), text, font=text_font)[2]
    chip_w = max(126, text_w + 86)
    rounded_rect(draw, (x, y, x + chip_w, y + chip_h), chip_h // 2, "#eef1f3")
    draw_upvote_icon(draw, x + 18, y + 16, icon, "#3f454b")
    draw.text((x + 54, y + 12), text, font=text_font, fill="#2f353b")
    return x + chip_w + 14


def draw_comment_button(draw, x, y, comments):
    chip_h = 54
    icon = 22
    text_font = font(28, True)
    text = compact_number(comments)
    text_w = draw.textbbox((0, 0), text, font=text_font)[2]
    chip_w = max(126, text_w + 86)
    rounded_rect(draw, (x, y, x + chip_w, y + chip_h), chip_h // 2, "#eef1f3")
    draw_comment_icon(draw, x + 18, y + 16, icon, "#3f454b")
    draw.text((x + 54, y + 12), text, font=text_font, fill="#2f353b")
    return x + chip_w + 14


def draw_action_row(draw, x, y, score, comments=None):
    next_x = draw_vote_group(draw, x, y, score)
    if comments is not None:
        draw_comment_button(draw, next_x, y, comments)


def draw_brand_below_card(draw, y2):
    brand = "@theredditstuff"
    brand_font = font(42, True)
    bbox = draw.textbbox((0, 0), brand, font=brand_font)
    draw.text(((W - (bbox[2] - bbox[0])) / 2, y2 + 34), brand, font=brand_font, fill=(255, 255, 255, 128))


def card_bounds(content_h):
    height = max(430, min(content_h, 940))
    y1 = (H - height) // 2
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
    draw.text((x, y + 36), "replied", font=weak_font, fill="#57606a")

    y += 100
    for line in body_lines:
        draw.text((x, y), line, font=body_font, fill="#111111")
        y += body_font.size + 17

    draw_action_row(draw, x, y2 - 104, segment.get("score", 0))
    draw_brand_below_card(draw, y2)


def draw_cta_component(draw, segment):
    text_font = font(54, False)
    lines = segment["text"].split("\n")
    content_h = 106 + len(lines) * (text_font.size + 17) + 82
    x1, y1, x2, y2 = card_bounds(content_h)
    rounded_rect(draw, (x1, y1, x2, y2), 28, "#ffffff")
    y = y1 + 92
    for line in lines:
        draw.text((x1 + 50, y), line, font=text_font, fill="#111111")
        y += text_font.size + 17
    draw_brand_below_card(draw, y2)


def make_card(segment, index, total):
    img = Image.new("RGB", (W, H), "#ff4500")
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


def segment_to_video(image_path, audio_path, video_path, duration):
    run_ffmpeg(
        [
            "-loop",
            "1",
            "-t",
            f"{duration:.2f}",
            "-i",
            str(image_path),
            "-i",
            str(audio_path),
            "-vf",
            "format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "stillimage",
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
            "voice": f"In {subreddit}, {post_author} asked: {title}",
        }
    ]
    for i, comment in enumerate(post["comments"][:4], start=1):
        body = " ".join(comment["body"].split())
        body = textwrap.shorten(body, width=230, placeholder="...")
        author = comment.get("author", "redditor")
        segments.append(
            {
                "kind": "comment",
                "label": f"Top reply {i}",
                "text": body,
                "author": author,
                "score": comment.get("score", 0),
                "voice": f"{author} replied: {body}",
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

    post = fetch_askreddit_post()
    segments = build_segments(post)
    STORY_OUT.write_text(json.dumps({"post": post, "segments": segments}, indent=2), encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="theredditstuff_") as tmp:
        work = Path(tmp)
        part_paths = []
        for index, segment in enumerate(segments):
            image_path = work / f"segment_{index:02}.png"
            audio_path = work / f"segment_{index:02}.wav"
            video_path = work / f"segment_{index:02}.mp4"

            make_card(segment, index, len(segments)).save(image_path)
            make_voice(segment["voice"], audio_path, index)
            duration = audio_duration(audio_path) + 0.15
            segment_to_video(image_path, audio_path, video_path, duration)
            part_paths.append(video_path)

        concat_file = work / "concat.txt"
        concat_file.write_text("".join(f"file '{path}'\n" for path in part_paths), encoding="utf-8")
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(VIDEO_OUT)])

    print(VIDEO_OUT)
    print(STORY_OUT)


if __name__ == "__main__":
    main()
