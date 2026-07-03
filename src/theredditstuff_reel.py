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
USE_LIVE_REDDIT = os.getenv("USE_LIVE_REDDIT", "0") == "1"

DEFAULT_SUBREDDITS = [
    "AskReddit",
    "hypotheticalsituation",
    "WouldYouRather",
    "NoStupidQuestions",
    "TooAfraidToAsk",
    "DoesAnybodyElse",
    "unpopularopinion",
]

EVERYDAY_TERMS = [
    "friend",
    "friends",
    "relationship",
    "dating",
    "partner",
    "couple",
    "couples",
    "family",
    "parents",
    "roommate",
    "neighbor",
    "work",
    "coworker",
    "boss",
    "money",
    "bill",
    "split",
    "text",
    "texts",
    "reply",
    "phone",
    "password",
    "home",
    "house",
    "habit",
    "small thing",
    "everyday",
    "normal",
    "rude",
    "annoying",
    "social",
    "people",
    "strangers",
    "restaurant",
    "shopping",
]

DEBATABLE_TERMS = [
    "rude",
    "normal",
    "weird",
    "wrong",
    "acceptable",
    "fair",
    "unfair",
    "judge",
    "red flag",
    "would you",
    "should",
    "shouldn't",
    "rather",
    "annoying",
    "harmless",
    "small lie",
]

LOW_VALUE_TERMS = [
    "billionaire",
    "millionaire",
    "rich",
    "wealthy",
    "celebrity",
    "famous",
    "movie",
    "movies",
    "anime",
    "game",
    "gaming",
    "song",
    "lyrics",
    "history",
    "science",
    "space",
    "states",
    "country",
    "countries",
]


SAMPLE_POSTS = [
    {
        "subreddit": "AskReddit",
        "author": "ordinary_opinion",
        "score": 48200,
        "num_comments": 9300,
        "title": "Is it rude to wear headphones at home when someone is talking nearby?",
        "source_url": "fallback://headphones-at-home-rude",
        "body": "",
        "comments": [
            {"author": "same_room_rules", "score": 21400, "body": "If someone is actively talking to you, headphones feel rude. If they are just existing nearby, that is called living in the same house."},
            {"author": "quiet_time_needed", "score": 18900, "body": "I wear headphones because I need my brain to calm down. It is not personal unless I ignore someone who clearly needs me."},
            {"author": "say_my_name_first", "score": 15100, "body": "The rule should be simple. Say my name first, wait for me to pause, then talk. Do not start a full story while I hear nothing."},
            {"author": "family_volume", "score": 12700, "body": "Some families think being available every second is normal. Other people need boundaries. That mismatch causes the whole argument."},
            {"author": "one_ear_out", "score": 9800, "body": "One earbud at home is the compromise. Full noise canceling during a conversation is basically a soft exit."},
            {"author": "not_a_call_center", "score": 7600, "body": "Nobody should have to be reachable like customer support just because they are sitting in the living room."},
            {"author": "context_matters", "score": 6100, "body": "If it is dinner or family time, rude. If it is random background noise at 9 PM, completely normal."},
        ],
    },
    {
        "subreddit": "WouldYouRather",
        "author": "bill_splitter",
        "score": 38600,
        "num_comments": 7200,
        "title": "Would you split the bill evenly if one friend ordered way more?",
        "source_url": "fallback://split-bill-evenly",
        "body": "",
        "comments": [
            {"author": "pay_for_yours", "score": 17600, "body": "No. Splitting evenly is for people who ordered roughly the same thing, not someone who discovered appetizers and cocktails."},
            {"author": "friendship_tax", "score": 14100, "body": "If it is a close friend and it happens once, I do not care. If it is a pattern, I am suddenly very good at math."},
            {"author": "say_it_early", "score": 11800, "body": "The easiest fix is saying separate checks before anyone orders. Waiting until the bill comes makes it awkward for everyone."},
            {"author": "generous_until_used", "score": 9400, "body": "I like being generous. I do not like being quietly assigned the role of discount code."},
            {"author": "group_pressure", "score": 8100, "body": "People call you cheap for objecting, but somehow the person ordering double is never called inconsiderate."},
            {"author": "depends_on_amount", "score": 6900, "body": "If the difference is five dollars, whatever. If the difference is thirty dollars, we are itemizing."},
            {"author": "birthday_exception", "score": 5300, "body": "Only exception is birthdays or planned treats. Otherwise your lobster is between you and your bank account."},
        ],
    },
    {
        "subreddit": "hypotheticalsituation",
        "author": "texting_gap",
        "score": 29400,
        "num_comments": 6100,
        "title": "Is it normal to not reply to texts for hours?",
        "source_url": "fallback://reply-to-texts-hours",
        "body": "",
        "comments": [
            {"author": "not_emergency_line", "score": 15300, "body": "Normal. A text is not a summons. If it is urgent, call me. If it is not urgent, I will answer when my brain returns."},
            {"author": "relationship_math", "score": 13700, "body": "It depends on the relationship. Taking six hours to answer your partner every single day sends a message whether you mean it or not."},
            {"author": "busy_is_real", "score": 9800, "body": "People are working, driving, sleeping, cooking, or just tired. Instant replies should not be the default expectation."},
            {"author": "pattern_reader", "score": 8900, "body": "The delay is not the problem. The pattern is. If someone only replies when they need something, you notice."},
            {"author": "phone_in_hand", "score": 7300, "body": "Everyone says they were away from their phone, but then posts three stories. That is the part that feels insulting."},
            {"author": "mental_space", "score": 6100, "body": "Sometimes I see the message and need time before I can be a normal person. That should be allowed."},
            {"author": "simple_update", "score": 4800, "body": "A quick 'busy, will reply later' solves most of this. People do not need instant access, they need basic consideration."},
        ],
    },
    {
        "subreddit": "NoStupidQuestions",
        "author": "phone_boundary",
        "score": 25100,
        "num_comments": 5400,
        "title": "Should couples share phone passwords or is that weird?",
        "source_url": "fallback://couples-phone-passwords",
        "body": "",
        "comments": [
            {"author": "trust_is_not_access", "score": 13200, "body": "Trust does not mean unlimited access. I trust my partner, but my group chats did not consent to being read."},
            {"author": "emergency_only", "score": 10600, "body": "We know each other's passwords for emergencies, but neither of us scrolls. That feels normal to me."},
            {"author": "privacy_is_healthy", "score": 9100, "body": "People confuse privacy with secrecy. You can be committed and still have a private device."},
            {"author": "nothing_to_hide", "score": 8200, "body": "If there is nothing to hide, sharing it should not be a big deal. The defensive reaction would worry me more than the password."},
            {"author": "bad_precedent", "score": 6700, "body": "Once checking becomes normal, it rarely stops at emergencies. It turns into little audits of tone, timing, and likes."},
            {"author": "depends_on_history", "score": 5400, "body": "If someone has cheated before, this conversation is different. But using passwords to rebuild trust sounds miserable."},
            {"author": "mutual_or_no", "score": 4200, "body": "It is only fair if it is mutual and calm. If one person demands it during a fight, that is not trust."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "tiny_judgement",
        "score": 34200,
        "num_comments": 6800,
        "title": "What harmless habit makes you instantly judge someone?",
        "source_url": "fallback://harmless-habit-judge",
        "body": "",
        "comments": [
            {"author": "speakerphone_public", "score": 17100, "body": "Watching videos out loud in public. It tells me they know other people exist and simply decided not to care."},
            {"author": "cart_blocker", "score": 13800, "body": "Blocking the whole grocery aisle with a cart while slowly comparing two identical boxes of cereal."},
            {"author": "late_every_time", "score": 11900, "body": "Being late every single time and acting like clocks are a personal attack."},
            {"author": "trash_next_to_bin", "score": 9600, "body": "Leaving trash near a bin but not inside it. You did ninety percent of the task and quit at the weirdest part."},
            {"author": "phone_dinner", "score": 8100, "body": "Checking their phone constantly during a meal. It makes the other person feel like a loading screen."},
            {"author": "reply_all_survivor", "score": 6500, "body": "Using reply all for something only one person needed to see. I immediately assume they create meetings too."},
            {"author": "doorway_pause", "score": 5100, "body": "Stopping right in a doorway to think. Move three steps and have your life crisis over there."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "price_check",
        "score": 31800,
        "num_comments": 7400,
        "title": "What everyday thing became expensive for no good reason?",
        "source_url": "fallback://everyday-expensive",
        "body": "",
        "comments": [
            {"author": "sandwich_math", "score": 16600, "body": "A basic sandwich. Somehow bread, cheese, and one sad tomato became a financial decision."},
            {"author": "coffee_total", "score": 14200, "body": "Coffee from normal places. I am not asking for a life-changing drink. I am asking to be awake."},
            {"author": "delivery_fees", "score": 12100, "body": "Food delivery. The fees now cost enough that I start negotiating with my own laziness."},
            {"author": "movie_snacks", "score": 9800, "body": "Popcorn at the movies. They price it like each kernel has a college degree."},
            {"author": "basic_groceries", "score": 8700, "body": "Groceries in general. You walk in for five normal items and leave feeling financially irresponsible."},
            {"author": "phone_cases", "score": 6900, "body": "Phone cases. It is a rectangle of plastic, but apparently it has luxury brand confidence."},
            {"author": "airport_water", "score": 5600, "body": "Bottled water at airports. Being thirsty should not feel like a subscription service."},
        ],
    },
    {
        "subreddit": "NoStupidQuestions",
        "author": "care_or_avoid",
        "score": 26700,
        "num_comments": 4900,
        "title": "What do people call self-care that is actually avoidance?",
        "source_url": "fallback://self-care-avoidance",
        "body": "",
        "comments": [
            {"author": "nap_loop", "score": 13100, "body": "Sleeping every time life gets stressful. Rest is healthy, but using sleep as an escape hatch catches up fast."},
            {"author": "buying_peace", "score": 11200, "body": "Buying things to feel better. Sometimes the package is not self-care, it is just tomorrow's regret in a box."},
            {"author": "cancel_everything", "score": 9300, "body": "Canceling plans every time you feel slightly uncomfortable. Boundaries are good, disappearing from your life is different."},
            {"author": "ignore_messages", "score": 7800, "body": "Ignoring every difficult message and calling it protecting your peace. Sometimes peace requires one awkward reply."},
            {"author": "doomscroll_break", "score": 6500, "body": "Scrolling for hours to decompress. If you feel worse afterward, it was not care."},
            {"author": "treat_yourself_loop", "score": 5200, "body": "Treating yourself after every minor inconvenience. At some point the treat becomes the main problem."},
            {"author": "no_hard_tasks", "score": 4100, "body": "Only doing things that feel good in the moment. Future you is still on the group project."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "small_lie",
        "score": 28900,
        "num_comments": 6200,
        "title": "What small lie does everyone tell?",
        "source_url": "fallback://small-lie-everyone-tells",
        "body": "",
        "comments": [
            {"author": "five_minutes", "score": 15100, "body": "I'll be ready in five minutes. That sentence has never once respected time as a concept."},
            {"author": "no_worries", "score": 12900, "body": "No worries. Sometimes there are absolutely worries, but the email needs to end."},
            {"author": "almost_there", "score": 10400, "body": "I'm almost there. Usually means I have left emotionally, but not physically."},
            {"author": "read_terms", "score": 8800, "body": "I have read and agree to the terms. No you did not. Nobody did. We all just wanted the app to open."},
            {"author": "doing_fine", "score": 7600, "body": "I'm fine. It can mean anything from actually fine to one inconvenience away from becoming a documentary."},
            {"author": "circle_back", "score": 6200, "body": "Let's circle back. Half the time it means let this idea fade away with dignity."},
            {"author": "just_one_episode", "score": 4900, "body": "Just one episode. That lie has destroyed more sleep schedules than caffeine."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "house_rules",
        "score": 24400,
        "num_comments": 5700,
        "title": "What is normal in your house but weird everywhere else?",
        "source_url": "fallback://normal-house-weird-elsewhere",
        "body": "",
        "comments": [
            {"author": "assigned_cups", "score": 12000, "body": "Everyone having a specific cup that nobody else is allowed to use. It sounds silly until someone touches the wrong cup."},
            {"author": "silent_room", "score": 10100, "body": "Sitting in the same room doing completely separate things in silence. To us it is quality time."},
            {"author": "leftover_rules", "score": 8900, "body": "Labeling leftovers by emotional importance. Some food is shared food. Some food is a legal matter."},
            {"author": "inside_voice", "score": 7300, "body": "Announcing where you are going in the house. Nobody needs to know, but everyone still reports their location."},
            {"author": "remote_owner", "score": 6100, "body": "One person being the unofficial owner of the TV remote. There was no election, but the power is real."},
            {"author": "shoe_border", "score": 5000, "body": "Shoes off is not a preference, it is a border policy."},
            {"author": "fridge_negotiation", "score": 3900, "body": "Asking if anyone owns food before eating it, even if it is clearly communal. Trust has limits near snacks."},
        ],
    },
    {
        "subreddit": "hypotheticalsituation",
        "author": "friend_warning",
        "score": 30100,
        "num_comments": 6600,
        "title": "Would you tell your friend if their partner was flirting with someone else?",
        "source_url": "fallback://tell-friend-partner-flirting",
        "body": "",
        "comments": [
            {"author": "tell_them_once", "score": 15400, "body": "Yes, but only with facts. I would say what I saw, not turn it into a courtroom drama."},
            {"author": "proof_first", "score": 13200, "body": "I need to be very sure before saying anything. A wrong accusation can damage three relationships at once."},
            {"author": "want_to_know", "score": 11100, "body": "I would want my friend to tell me, so I have to offer the same honesty back."},
            {"author": "messenger_problem", "score": 9400, "body": "People always say they want the truth until you become the person delivering it."},
            {"author": "depends_on_flirting", "score": 7800, "body": "There is playful conversation and then there is clearly testing the waters. The difference matters."},
            {"author": "private_first", "score": 6400, "body": "I might talk to the partner first if we are close. Sometimes one direct warning fixes stupid behavior."},
            {"author": "no_group_chat", "score": 5200, "body": "Whatever happens, do not make it group chat gossip. Tell the friend privately or stay out of it."},
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


def strip_emoji(text):
    text = re.sub(
        "["
        "\U0001f1e6-\U0001f1ff"
        "\U0001f300-\U0001f5ff"
        "\U0001f600-\U0001f64f"
        "\U0001f680-\U0001f6ff"
        "\U0001f700-\U0001f77f"
        "\U0001f780-\U0001f7ff"
        "\U0001f800-\U0001f8ff"
        "\U0001f900-\U0001f9ff"
        "\U0001fa00-\U0001fa6f"
        "\U0001fa70-\U0001faff"
        "\u2600-\u27bf"
        "]+",
        "",
        text or "",
    )
    return " ".join(text.split())


def term_in_text(term, text):
    if " " in term:
        return term in text
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def is_everyday_topic(title):
    lower = (title or "").lower()
    return any(term_in_text(term, lower) for term in EVERYDAY_TERMS) and any(
        term_in_text(term, lower) for term in DEBATABLE_TERMS
    )


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
        if not is_everyday_topic(data.get("title", "")):
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
        if not is_everyday_topic(title):
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
    if not USE_LIVE_REDDIT:
        return fallback_post()

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

    score += sum(12 for word in EVERYDAY_TERMS if term_in_text(word, title))
    score += sum(18 for word in DEBATABLE_TERMS if term_in_text(word, title))
    score += min((post.get("num_comments") or 0) / 150, 25)
    score += min((post.get("score") or 0) / 2000, 20)
    if post.get("subreddit") in DEFAULT_SUBREDDITS[:3]:
        score += 8

    if 6 <= len(words) <= 18:
        score += 18
    if len(title) > 135:
        score -= 30
    if any(term_in_text(word, title) for word in LOW_VALUE_TERMS):
        score -= 35
    if title.startswith(("what's your favorite", "what is your favorite", "what are your favorite")):
        score -= 30
    if not is_everyday_topic(title):
        score -= 100
    if not is_safe_text(title):
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
    action_space = 28
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

    draw_brand_below_card(draw, y2)


def draw_comment_component(draw, segment):
    pad = 50
    body_font = font(54, False)
    author_font = font(31, True)
    weak_font = font(28, False)
    max_width = W - 64 * 2 - pad * 2
    body_lines = wrap(draw, segment["text"], max_width, body_font)[:9]
    action_space = 28
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


def build_segments(post):
    title = strip_emoji(post["title"].strip())
    subreddit = post.get("subreddit", "AskReddit")
    post_author = post.get("author", "redditor")
    segments = [
        {
            "kind": "post",
            "label": "Post",
            "text": title,
            "body": strip_emoji(post.get("body", "")),
            "author": post_author,
            "subreddit": subreddit,
            "score": None,
            "num_comments": None,
            "voice": title,
        }
    ]
    for i, comment in enumerate(post["comments"][:MAX_COMMENTS], start=1):
        body = strip_emoji(comment["body"])
        body = textwrap.shorten(body, width=230, placeholder="...")
        author = comment.get("author", "redditor")
        segments.append(
            {
                "kind": "comment",
                "label": f"Top reply {i}",
                "text": body,
                "author": author,
                "intro": "commented",
                "score": None,
                "voice": body,
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
