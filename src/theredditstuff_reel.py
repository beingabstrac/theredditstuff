#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
VIDEO_OUT = OUT / "theredditstuff_mvp.mp4"
STORY_OUT = OUT / "theredditstuff_storyboard.json"

W, H = 1080, 1920


SAMPLE_POST = {
    "subreddit": "AskReddit",
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
        "subreddit": "AskReddit",
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
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/Library/Fonts/Arial.ttf",
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


def make_card(segment, index, total):
    img = Image.new("RGB", (W, H), "#ff4500")
    draw = ImageDraw.Draw(img)

    brand_font = font(58, True)
    body_font = font(66, False)

    # Simple Reddit-style mark.
    draw.ellipse((88, 92, 178, 182), fill="white")
    draw.ellipse((112, 122, 128, 138), fill="#ff4500")
    draw.ellipse((138, 122, 154, 138), fill="#ff4500")
    draw.arc((116, 132, 150, 162), 10, 170, fill="#ff4500", width=5)
    draw.line((162, 100, 192, 72), fill="white", width=8)
    draw.ellipse((188, 62, 210, 84), fill="white")
    draw.text((228, 105), "@theredditstuff", font=brand_font, fill="white")

    card_x1, card_y1 = 70, 365
    card_x2, card_y2 = W - 70, 1510
    rounded_rect(draw, (card_x1, card_y1, card_x2, card_y2), 22, "#f8f8f8")
    draw_multiline(
        draw,
        segment["text"],
        (card_x1 + 58, card_y1 + 72),
        card_x2 - card_x1 - 96,
        body_font,
        "#1c1c1c",
        line_gap=26,
        max_lines=10,
    )
    return img


def run_ffmpeg(args):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def make_voice(text, audio_path, index):
    if kokoro_voice(text, audio_path, index):
        return

    tts = shutil.which("espeak-ng")
    if not tts:
        raise RuntimeError("No local TTS found. Install Kokoro or espeak-ng.")
    voice = "en-us+m3" if index % 2 else "en-us+f3"
    subprocess.run([tts, "-v", voice, "-s", "155", "-w", str(audio_path), text], check=True)


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
    segments = [
        {
            "label": "Post",
            "text": title,
            "voice": f"Reddit asked: {title}",
        }
    ]
    for i, comment in enumerate(post["comments"][:4], start=1):
        body = " ".join(comment["body"].split())
        body = textwrap.shorten(body, width=230, placeholder="...")
        segments.append(
            {
                "label": f"Top reply {i}",
                "text": body,
                "score": comment.get("score", 0),
                "voice": body,
            }
        )

    cta = cta_for_title(title)
    segments.append(
        {
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
            duration = audio_duration(audio_path) + 0.3
            segment_to_video(image_path, audio_path, video_path, duration)
            part_paths.append(video_path)

        concat_file = work / "concat.txt"
        concat_file.write_text("".join(f"file '{path}'\n" for path in part_paths), encoding="utf-8")
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(VIDEO_OUT)])

    print(VIDEO_OUT)
    print(STORY_OUT)


if __name__ == "__main__":
    main()
