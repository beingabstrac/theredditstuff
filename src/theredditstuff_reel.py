#!/usr/bin/env python3
import json
import asyncio
import html
import os
import re
import shutil
import sys
import subprocess
import tempfile
import textwrap
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEPS = ROOT / ".deps"
OUT = ROOT / "outputs"
VIDEO_OUT = OUT / "theredditstuff_mvp.mp4"
STORY_OUT = OUT / "theredditstuff_storyboard.json"
ICON_DIR = ROOT / "assets" / "icons"
FONT_DIR = ROOT / "assets" / "fonts"
POSTED_SOURCES_FILE = Path(os.getenv("POSTED_SOURCES_FILE", ROOT / "data" / "posted_sources.json"))

W, H = 1080, 1920
BRAND_GAP = 34
BRAND_SPACE = 96
MAX_COMMENTS = int(os.getenv("MAX_COMMENTS", "7"))
RSS_CANDIDATE_TARGET = int(os.getenv("RSS_CANDIDATE_TARGET", "12"))
RSS_COMMENT_ATTEMPTS = int(os.getenv("RSS_COMMENT_ATTEMPTS", "2"))

DEFAULT_SUBREDDITS = [
    "AskReddit",
    "hypotheticalsituation",
    "WouldYouRather",
    "NoStupidQuestions",
    "TooAfraidToAsk",
    "DoesAnybodyElse",
    "unpopularopinion",
]


SAMPLE_POSTS = [
    {
        "subreddit": "AskReddit",
        "author": "ordinary_opinion",
        "score": 48200,
        "num_comments": 9300,
        "title": "What is socially acceptable but actually rude?",
        "source_url": "fallback://socially-acceptable-rude",
        "body": "",
        "comments": [
            {"author": "speakerphone_truth", "score": 21400, "body": "Putting someone on speakerphone without telling the other people in the room. It instantly changes the whole conversation."},
            {"author": "early_is_rude", "score": 18900, "body": "Showing up way too early to someone's house. Five minutes is fine. Thirty minutes early is just a surprise inspection."},
            {"author": "dont_ask_that", "score": 15100, "body": "Asking couples when they are having kids. People treat it like small talk, but it can be a really loaded question."},
            {"author": "public_not_content", "score": 12700, "body": "Recording strangers in public for content. Everyone acts like it is normal now, but most people did not agree to be part of your video."},
            {"author": "smalltalk_skeptic", "score": 9800, "body": "Commenting on someone's body, even as a compliment. You never know what they are dealing with."},
            {"author": "meeting_escapee", "score": 7600, "body": "Starting a meeting five minutes before it ends with 'quick question.' It is never quick."},
            {"author": "cart_conflict", "score": 6100, "body": "Leaving your shopping cart in the middle of the aisle while you browse like nobody else exists."},
        ],
    },
    {
        "subreddit": "WouldYouRather",
        "author": "choice_pressure",
        "score": 38600,
        "num_comments": 7200,
        "title": "Would you rather be liked by everyone but never respected, or respected by everyone but rarely liked?",
        "source_url": "fallback://liked-or-respected",
        "body": "",
        "comments": [
            {"author": "respect_first", "score": 17600, "body": "Respect, easily. Being liked by everyone usually means you are editing yourself all day."},
            {"author": "social_battery_low", "score": 14100, "body": "Liked but not respected sounds exhausting. People would invite you everywhere and still ignore what you say."},
            {"author": "depends_on_work", "score": 11800, "body": "At work I want respect. In normal life I would rather be liked. Context changes the answer completely."},
            {"author": "quiet_boundary", "score": 9400, "body": "Respected but rarely liked. At least people would take my boundaries seriously."},
            {"author": "not_that_simple", "score": 8100, "body": "If everyone likes you, some respect probably comes with it. If nobody likes you, respect can turn into fear pretty fast."},
            {"author": "people_pleaser_exit", "score": 6900, "body": "I spent years trying to be liked. Respect gives you peace. Being liked gives you maintenance work."},
            {"author": "middle_option", "score": 5300, "body": "The real answer is neither. Both sound like a lonely life with better branding."},
        ],
    },
    {
        "subreddit": "hypotheticalsituation",
        "author": "tiny_tradeoff",
        "score": 29400,
        "num_comments": 6100,
        "title": "You get free rent forever, but one random friend can walk into your home anytime. Do you take it?",
        "source_url": "fallback://free-rent-random-friend",
        "body": "",
        "comments": [
            {"author": "rent_is_winning", "score": 15300, "body": "Free rent forever is too much money to turn down. I would simply stop having random friends."},
            {"author": "privacy_tax", "score": 13700, "body": "No. Home is the one place where I do not want surprise guests, even if the surprise is technically affordable."},
            {"author": "doorbell_required", "score": 9800, "body": "Depends if they can walk in while I am sleeping. If yes, absolutely not. That is not free rent, that is a haunted lease."},
            {"author": "city_prices", "score": 8900, "body": "In this economy, my friend can walk in and critique my furniture. I will be financially healing."},
            {"author": "social_contract", "score": 7300, "body": "I would take it only if I can choose the friend group. Some people treat boundaries like suggestions."},
            {"author": "lock_the_bathroom", "score": 6100, "body": "Free rent but zero privacy is still a bad deal. People underestimate how much peace is worth."},
            {"author": "one_good_friend", "score": 4800, "body": "If it is one of my close friends, fine. If it includes acquaintances, the deal is dead immediately."},
        ],
    },
    {
        "subreddit": "NoStupidQuestions",
        "author": "social_confused",
        "score": 25100,
        "num_comments": 5400,
        "title": "Is it weird to stop being friends with someone just because they only talk about themselves?",
        "source_url": "fallback://self-centered-friend",
        "body": "",
        "comments": [
            {"author": "conversation_is_two", "score": 13200, "body": "No. A friendship where you are only an audience member is not really a friendship."},
            {"author": "slow_fade_fan", "score": 10600, "body": "It is not weird, but I would probably fade out instead of making a dramatic announcement."},
            {"author": "ask_once", "score": 9100, "body": "I would bring it up once. Some people genuinely do not realize they are doing it."},
            {"author": "not_a_podcast", "score": 8200, "body": "If every hangout feels like listening to a podcast you cannot pause, that is a valid reason to leave."},
            {"author": "pattern_matters", "score": 6700, "body": "Everyone has self-centered phases. The issue is when it becomes the whole pattern."},
            {"author": "emotional_labor_bill", "score": 5400, "body": "People call it rude to leave, but never rude to use someone as free emotional storage."},
            {"author": "direct_but_kind", "score": 4200, "body": "Tell them kindly first. If nothing changes, you already gave the friendship a fair chance."},
        ],
    },
]

SAMPLE_POST = SAMPLE_POSTS[0]

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
    "government",
    "president",
    "u.s.",
    "us state",
    "u.s. state",
    "america",
    "american",
    "independent country",
    "country overnight",
    "countries",
    "border",
    "military",
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


def load_posted_sources():
    try:
        data = json.loads(POSTED_SOURCES_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set()
    except json.JSONDecodeError:
        return set()
    return {item.get("source_url") for item in data.get("posted", []) if item.get("source_url")}


def fallback_post():
    raw_index = os.getenv("FALLBACK_POST_INDEX") or os.getenv("GITHUB_RUN_NUMBER") or os.getenv("GITHUB_RUN_ID")
    index = int(raw_index) if raw_index and raw_index.isdigit() else int(time.time() // 3600)
    posted_sources = load_posted_sources()
    for offset in range(len(SAMPLE_POSTS)):
        post = SAMPLE_POSTS[(index + offset) % len(SAMPLE_POSTS)]
        if post.get("source_url") not in posted_sources:
            return json.loads(json.dumps(post))
    return json.loads(json.dumps(SAMPLE_POSTS[index % len(SAMPLE_POSTS)]))


def candidate_source_url(post):
    return post.get("source_url") or f"https://www.reddit.com{post.get('permalink', '')}"


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


def reddit_rss_request(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "theredditstuff-rss/0.1",
            "Accept": "application/atom+xml, application/rss+xml, text/xml",
        },
    )
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == 1:
                raise
            wait = int(exc.headers.get("x-ratelimit-reset") or 12)
            time.sleep(max(8, min(wait + 1, 20)))


def rss_entries(url):
    root = ET.fromstring(reddit_rss_request(url))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    return root.findall("a:entry", ns), ns


def clean_rss_html(value):
    text = html.unescape(value or "")
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def rss_author(entry, ns):
    node = entry.find("a:author/a:name", ns)
    return (node.text or "redditor").removeprefix("/u/") if node is not None else "redditor"


def rss_link(entry, ns):
    node = entry.find("a:link", ns)
    return node.attrib.get("href", "") if node is not None else ""


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


def fetch_subreddit_rss_candidates(subreddit):
    url = f"https://www.reddit.com/r/{subreddit}/top/.rss?t=day"
    try:
        entries, ns = rss_entries(url)
    except Exception as exc:
        print(f"Skipping RSS r/{subreddit}: {exc}")
        return []

    candidates = []
    for entry in entries:
        title = entry.findtext("a:title", default="", namespaces=ns).strip()
        link = rss_link(entry, ns)
        post_id = entry.findtext("a:id", default="", namespaces=ns).removeprefix("t3_")
        if not title or not link or not post_id:
            continue
        if not is_safe_text(title):
            continue
        permalink = urllib.parse.urlparse(link).path
        candidates.append(
            {
                "id": post_id,
                "subreddit": subreddit,
                "author": rss_author(entry, ns),
                "score": None,
                "num_comments": None,
                "title": title,
                "selftext": "",
                "permalink": permalink,
                "source_url": link,
                "from_rss": True,
            }
        )
        if len(candidates) >= RSS_CANDIDATE_TARGET:
            break
    return candidates


def fetch_rss_comments(permalink):
    url = f"https://www.reddit.com{permalink.rstrip('/')}/.rss?sort=top"
    try:
        entries, ns = rss_entries(url)
    except Exception as exc:
        print(f"RSS comments unavailable: {exc}")
        return []

    comments = []
    for entry in entries:
        entry_id = entry.findtext("a:id", default="", namespaces=ns)
        if not entry_id.startswith("t1_"):
            continue
        body = clean_rss_html(entry.findtext("a:content", default="", namespaces=ns))
        author = rss_author(entry, ns)
        if len(body) < 35 or not is_safe_text(body, author):
            continue
        comments.append({"author": author, "score": None, "body": body})
        if len(comments) >= MAX_COMMENTS:
            break
    return comments


def fetch_reddit_post():
    token = reddit_token()

    candidates = []
    if token:
        for subreddit in subreddit_pool():
            candidates.extend(fetch_subreddit_candidates(token, subreddit))
    else:
        for subreddit in subreddit_pool():
            candidates.extend(fetch_subreddit_rss_candidates(subreddit))
            if len(candidates) >= RSS_CANDIDATE_TARGET:
                break
    if not candidates:
        return fallback_post()

    posted_sources = load_posted_sources()
    fresh_candidates = [post for post in candidates if candidate_source_url(post) not in posted_sources]
    if fresh_candidates:
        candidates = fresh_candidates

    picked = max(candidates, key=shareable_score)

    comments = []
    if picked.get("from_rss"):
        for candidate in sorted(candidates, key=shareable_score, reverse=True)[:RSS_COMMENT_ATTEMPTS]:
            comments = fetch_rss_comments(candidate["permalink"])
            if comments:
                picked = candidate
                break
        if not comments:
            return fallback_post()
    else:
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

    if not comments:
        comments = fallback_post()["comments"]

    return {
        "subreddit": picked.get("subreddit", "AskReddit"),
        "author": picked.get("author", "redditor"),
        "score": picked.get("score", 0),
        "num_comments": picked.get("num_comments", 0),
        "title": picked["title"],
        "body": picked.get("selftext", ""),
        "comments": comments[:MAX_COMMENTS],
        "source_url": picked.get("source_url") or f"https://www.reddit.com{picked['permalink']}",
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
    score += min((post.get("num_comments") or 0) / 150, 25)
    score += min((post.get("score") or 0) / 2000, 20)
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
        FONT_DIR / "Inter.ttf",
        "/Library/Fonts/SF-Pro-Text-Bold.otf" if bold else "/Library/Fonts/SF-Pro-Text-Regular.otf",
        "/Library/Fonts/SF-Pro-Display-Bold.otf" if bold else "/Library/Fonts/SF-Pro-Display-Regular.otf",
        "/usr/share/fonts/truetype/inter/Inter-Bold.ttf" if bold else "/usr/share/fonts/truetype/inter/Inter-Regular.ttf",
        "/usr/share/fonts/truetype/inter-vf/Inter.var.ttf",
        "/usr/share/fonts/truetype/inter/Inter.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            loaded = ImageFont.truetype(candidate, size)
            if Path(candidate).name == "Inter.ttf":
                try:
                    loaded.set_variation_by_axes([14, 700 if bold else 400])
                except Exception:
                    pass
            return loaded
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
    icon = 20
    gap = 12
    left_pad = 18
    right_pad = 22
    text_font = font(27, False)
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
    next_x = x
    if score is not None:
        next_x = draw_vote_group(draw, x, y, score)
    if comments is not None and comments > 0:
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
    has_actions = segment.get("score") is not None or (segment.get("num_comments") or 0) > 0
    action_space = 104 if has_actions else 28
    content_h = 60 + 58 + len(title_lines) * (title_font.size + 17) + action_space + 52
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

    if has_actions:
        draw_action_row(draw, x, y2 - 104, segment.get("score"), segment.get("num_comments"))
    draw_brand_below_card(draw, y2)


def draw_comment_component(draw, segment):
    pad = 50
    body_font = font(54, False)
    author_font = font(31, True)
    weak_font = font(28, False)
    max_width = W - 64 * 2 - pad * 2
    body_lines = wrap(draw, segment["text"], max_width, body_font)[:9]
    has_actions = segment.get("score") is not None
    action_space = 104 if has_actions else 28
    content_h = 60 + 55 + len(body_lines) * (body_font.size + 17) + action_space + 52

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

    if has_actions:
        draw_action_row(draw, x, y2 - 104, segment.get("score"))
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
            "-af",
            "apad",
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
            "-t",
            f"{duration:.2f}",
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


def spoken_username(username):
    return (username or "someone").replace("_", " ").replace("-", " ")


def comment_voice_intro(body, index):
    lower = body.lower()
    if lower.rstrip().endswith("?"):
        return "asks"
    if any(word in lower for word in ["i think", "i believe", "imo", "in my opinion"]):
        return "thinks"
    if any(word in lower for word in ["i feel", "feels", "felt"]):
        return "feels"
    if any(word in lower for word in ["but", "though", "also", "another"]):
        return "adds"
    if any(word in lower for word in ["should", "never", "always", "normal now"]):
        return "says"
    return "says"


def comment_voice_line(author, body, index):
    name = spoken_username(author)
    intro = comment_voice_intro(body, index)
    return f"{name} {intro}: {body}"


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
    for i, comment in enumerate(post["comments"][:MAX_COMMENTS], start=1):
        body = " ".join(comment["body"].split())
        body = textwrap.shorten(body, width=230, placeholder="...")
        author = comment.get("author", "redditor")
        segments.append(
            {
                "kind": "comment",
                "label": f"Top reply {i}",
                "text": body,
                "author": author,
                "intro": "commented",
                "score": comment.get("score", 0),
                "voice": comment_voice_line(author, body, i),
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
            duration = audio_duration(audio_path) + 0.22
            segment_to_video(image_path, audio_path, video_path, duration)
            part_paths.append(video_path)

        concat_file = work / "concat.txt"
        concat_file.write_text("".join(f"file '{path}'\n" for path in part_paths), encoding="utf-8")
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(VIDEO_OUT)])

    print(VIDEO_OUT)
    print(STORY_OUT)


if __name__ == "__main__":
    main()
