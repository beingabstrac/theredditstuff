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
CURATED_POSTS_FILE = Path(os.getenv("CURATED_POSTS_FILE", ROOT / "data" / "curated_posts.json"))

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


BUCKET_ORDER = [
    "money",
    "texting",
    "work",
    "roommates",
    "family",
    "dating",
    "etiquette",
    "red_flags",
    "would_you_rather",
    "shopping",
    "friendship",
    "restaurant",
]

BUCKET_KEYWORDS = {
    "money": ["money", "bill", "split", "pay", "paid", "borrow", "lend", "rent", "expensive", "cheap", "tip"],
    "texting": ["text", "reply", "read", "phone", "message", "group chat"],
    "work": ["work", "boss", "coworker", "meeting", "office", "job", "manager"],
    "roommates": ["roommate", "house", "home", "neighbor", "apartment"],
    "family": ["family", "parents", "sibling", "relative", "mom", "dad"],
    "dating": ["dating", "date", "partner", "couple", "relationship"],
    "etiquette": ["rude", "normal", "weird", "manners", "invite", "guest"],
    "red_flags": ["red flag", "judge", "lose respect", "annoying", "habit"],
    "would_you_rather": ["would you rather"],
    "shopping": ["shopping", "store", "cart", "checkout", "delivery"],
    "friendship": ["friend", "friends", "friendship"],
    "restaurant": ["restaurant", "dinner", "food", "server", "coffee"],
}

QUESTION_FRAMES = [
    "Is it rude to {action} {context}?",
    "Is it normal to {action} {context}?",
    "Would you judge someone for choosing to {action} {context}?",
    "Should people be able to {action} {context}?",
    "Is it weird to {action} {context}?",
    "Would you say something if someone wanted to {action} {context}?",
]

PROCEDURAL_ANGLES = {
    "money": {
        "actions": ["ask the price", "split the bill exactly", "remind someone they owe money", "say something is too expensive", "refuse to lend money", "ask for separate checks", "skip plans because of cost", "charge a friend for gas"],
        "contexts": ["before agreeing to plans", "with close friends", "on a group dinner", "after someone already paid", "when everyone earns differently", "during a birthday plan", "after it happened twice", "without making it awkward"],
    },
    "texting": {
        "actions": ["reply late", "leave someone on read", "send only voice notes", "mute a group chat", "double text", "watch a story before replying", "send dry replies", "take a day to answer"],
        "contexts": ["when the message is casual", "while still posting online", "without explaining why", "after making plans", "during a busy workday", "in early dating", "with close friends", "when nothing is urgent"],
    },
    "work": {
        "actions": ["ignore work messages", "leave exactly on time", "say no to last minute tasks", "wear headphones all day", "skip optional meetings", "ask if a meeting is needed", "mute work apps", "refuse unpaid extra work"],
        "contexts": ["after hours", "during lunch", "while on vacation", "when coworkers keep doing it", "at a new job", "when the team is busy", "without apologizing", "if the manager expects it"],
    },
    "roommates": {
        "actions": ["label your food", "ask before guests come over", "complain about dishes", "change the thermostat", "avoid your roommate", "ask for quiet hours", "split chores exactly", "mention a bad smell"],
        "contexts": ["in a shared apartment", "after it keeps happening", "when rent is split evenly", "with a close friend roommate", "before saying anything else", "without sounding controlling", "when guests stay late", "if nobody else cleans"],
    },
    "family": {
        "actions": ["set boundaries", "skip a family event", "not answer calls immediately", "ask family to call first", "refuse a family favor", "leave early", "stop explaining every plan", "say a topic is off limits"],
        "contexts": ["with relatives", "as an adult", "during holidays", "when they mean well", "after repeated comments", "without feeling guilty", "when you need rest", "if they get offended"],
    },
    "dating": {
        "actions": ["split the bill", "ask about money", "need alone time", "keep phone privacy", "cancel a date", "share locations", "text after a date", "notice a small red flag"],
        "contexts": ["early in dating", "in a serious relationship", "on a first date", "without making it a big deal", "after one awkward moment", "when expectations are different", "if trust already exists", "before it becomes a pattern"],
    },
    "etiquette": {
        "actions": ["arrive early", "cancel by text", "ask guests to leave", "play videos out loud", "bring your own food", "ask why someone is quiet", "take leftovers", "ask people to remove shoes"],
        "contexts": ["at someone house", "in public", "during dinner", "when nobody asked", "with new friends", "after plans were made", "without warning", "if everyone else is comfortable"],
    },
    "red_flags": {
        "actions": ["judge a tiny habit", "notice how someone treats staff", "care about small lies", "pull back after one weird moment", "watch how someone handles no", "notice constant interrupting", "question a harmless habit", "trust your first impression"],
        "contexts": ["when meeting someone new", "on a first dinner", "in a friendship", "before anything serious happens", "even if it seems small", "when everyone else ignores it", "after it happens twice", "without overthinking it"],
    },
    "would_you_rather": {
        "actions": ["have free rent or free food", "always be early or exactly on time", "know the truth or feel comfortable", "have one close friend or many casual friends", "never wash dishes or never do laundry", "be respected or liked", "never wait in lines or never sit in traffic", "get honest advice or quiet support"],
        "contexts": ["for the rest of your life", "if you had to choose today", "with no explanation", "but everyone knows your choice", "if it changed your daily routine", "without being able to switch", "in your current life", "if money was still the same"],
    },
    "shopping": {
        "actions": ["leave items in the wrong place", "block an aisle", "take too long at self checkout", "argue over a return", "compare prices out loud", "leave a cart behind", "browse without buying", "take a call in line"],
        "contexts": ["in a busy store", "when people are waiting", "with friends nearby", "if staff have to fix it", "during checkout", "without noticing others", "when the line is long", "after changing your mind"],
    },
    "friendship": {
        "actions": ["stop texting first", "ask before venting", "exclude one friend from plans", "keep score of favors", "cancel for alone time", "tell a friend they are draining", "pull back quietly", "expect friends to remember details"],
        "contexts": ["in a close friendship", "after months of imbalance", "without starting drama", "when everyone is busy", "if they never ask about you", "after they cancel often", "when plans are small", "if it feels one-sided"],
    },
    "restaurant": {
        "actions": ["split appetizers", "complain loudly", "stay after eating", "take a call at dinner", "ask for many substitutions", "order the cheapest thing", "start a tipping debate", "share food without asking"],
        "contexts": ["at a restaurant", "with friends", "when the table is full", "during a first meetup", "if everyone is hungry", "after the server leaves", "when one person picked the place", "without making dinner tense"],
    },
}

PROCEDURAL_COMMENTS = {
    "money": ["The money is not the awkward part. The silence around it is.", "A clear expectation before plans saves everyone later.", "If someone is comfortable spending your money, that matters.", "Being careful with money is not the same as being cheap.", "The pattern matters more than the one moment."],
    "texting": ["Nobody needs instant access, but people do notice patterns.", "A quick honest reply prevents most of the drama.", "The same behavior feels different depending on the relationship.", "Delayed is normal. Dismissive is different.", "People overthink texting because nobody says the rules out loud."],
    "work": ["Work boundaries only seem rude when people benefit from ignoring them.", "If everything is urgent, nothing is being managed well.", "Being reliable should not mean being available forever.", "The job matters, but unpaid time still matters.", "One exception is fine. A permanent expectation is not."],
    "roommates": ["Shared space only works when everyone remembers it is shared.", "The problem is usually the repeat, not the one mistake.", "A house rule is fair if everyone has to live with the outcome.", "Quiet resentment makes roommate problems worse.", "Basic respect should not need a weekly negotiation."],
    "family": ["Family can explain why it is sensitive, not why boundaries disappear.", "Meaning well does not automatically make something okay.", "A calm no should not become a family emergency.", "Some relatives confuse closeness with permission.", "Adult relationships need respect more than constant access."],
    "dating": ["Small moments show expectations faster than big speeches.", "Privacy and secrecy are different, but people mix them up.", "Dating is easier when people say what they expect.", "One awkward moment is human. A pattern is information.", "The right person should make boundaries easier, not harder."],
    "etiquette": ["The difference between relaxed and rude is usually consent.", "A quick ask would solve most of these situations.", "Small manners matter because other people share the space.", "It is only normal if everyone involved is actually comfortable.", "Tone can turn a normal request into a rude one."],
    "red_flags": ["Tiny things matter because they often repeat.", "It is not the habit. It is refusing to notice the effect.", "How someone acts when nothing is at stake tells you a lot.", "A small red flag is usually selfishness showing up early.", "Some things are small until you imagine them every day."],
    "would_you_rather": ["This depends entirely on what is stressing you out right now.", "The practical answer and the emotional answer are different.", "One option gives comfort. The other gives control.", "People answer these based on this week pain.", "The right choice is the one that removes daily stress."],
    "shopping": ["Stores reveal who remembers other people exist.", "Being slow is fine. Being unaware is the problem.", "If your convenience creates work for strangers, it is not harmless.", "Most shopping etiquette is just moving out of the way.", "Small public habits become big because everyone shares the space."],
    "friendship": ["Friendship should not feel like one person renewing a subscription.", "The test is what happens when you stop carrying it.", "One-sided friendships can look normal from outside.", "Healthy friendship has room for both people to need things.", "People show priorities through effort, not speeches."],
    "restaurant": ["Restaurants are a quick test of patience and manners.", "The request is usually fine. The tone is what ruins it.", "How someone treats staff says a lot.", "Dinner should not become a public incident.", "Sharing only works when everyone agreed to share."],
}

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
            {"author": "treat_yourself_loop", "score": 5200, "body": "Treating yourself after every small inconvenience. At some point the treat becomes the main problem."},
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
            {"author": "remote_owner", "score": 6100, "body": "One person being the unofficial owner of the TV remote. Nobody voted, but the power is real."},
            {"author": "shoe_border", "score": 5000, "body": "Shoes off is not a preference, it is a house rule."},
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
    {
        "subreddit": "AskReddit",
        "author": "receipt_reader",
        "score": 27600,
        "num_comments": 5900,
        "title": "Is it rude to check the bill when someone else said they split it already?",
        "source_url": "fallback://check-split-bill",
        "body": "",
        "comments": [
            {"author": "math_is_not_rude", "score": 14100, "body": "Checking math is not rude. Making someone feel weird for checking is how people get overcharged."},
            {"author": "trust_but_receipt", "score": 11800, "body": "I trust my friends. I do not trust restaurants, service fees, or someone doing mental math after two drinks."},
            {"author": "quiet_check", "score": 9600, "body": "Just glance at it quietly. Turning it into an audit at the table is the part that gets awkward."},
            {"author": "pattern_problem", "score": 7600, "body": "If it happens once, no big deal. If the same person always handles the split and it always benefits them, check every time."},
            {"author": "money_boundary", "score": 5900, "body": "People act like caring about ten dollars is cheap. Ten dollars is lunch tomorrow."},
        ],
    },
    {
        "subreddit": "NoStupidQuestions",
        "author": "reply_speed",
        "score": 24100,
        "num_comments": 5200,
        "title": "Is leaving someone on read worse than replying late?",
        "source_url": "fallback://left-on-read-vs-late",
        "body": "",
        "comments": [
            {"author": "late_is_fine", "score": 12800, "body": "Replying late feels normal. Leaving me on read feels like you opened the door, saw me, and slowly closed it."},
            {"author": "not_a_contract", "score": 10300, "body": "Read receipts turned normal texting into performance management. I turned mine off for peace."},
            {"author": "depends_on_message", "score": 8700, "body": "If it is a meme, who cares. If it is a serious question, leaving it on read says a lot."},
            {"author": "brain_buffering", "score": 7100, "body": "Sometimes I read something and need time to answer properly. That is not ignoring, that is loading."},
            {"author": "say_busy", "score": 5500, "body": "A quick 'I'll reply later' fixes most of this. People usually want acknowledgment, not instant access."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "roommate_rules",
        "score": 32900,
        "num_comments": 8100,
        "title": "What roommate habit would make you move out immediately?",
        "source_url": "fallback://roommate-habit-move-out",
        "body": "",
        "comments": [
            {"author": "dirty_dishes_law", "score": 16800, "body": "Leaving dishes until they become a second ecosystem. I can handle clutter, not biological research."},
            {"author": "borrowed_without_asking", "score": 13900, "body": "Using my stuff and pretending it is communal. If I paid for it alone, it is not house property."},
            {"author": "midnight_guests", "score": 11600, "body": "Bringing people over at midnight without warning. Rent does not include surprise strangers in the kitchen."},
            {"author": "thermostat_war", "score": 9100, "body": "Changing the thermostat dramatically and denying it. I can forgive many things, but not climate crimes."},
            {"author": "trash_denial", "score": 7400, "body": "Seeing a full trash bag and adding one more thing like physics is someone else's problem."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "work_boundary",
        "score": 28400,
        "num_comments": 6100,
        "title": "Is it fair to ignore work messages after hours?",
        "source_url": "fallback://ignore-work-after-hours",
        "body": "",
        "comments": [
            {"author": "paid_hours_only", "score": 14900, "body": "If I am not being paid, I am not available. Emergencies need emergency pay."},
            {"author": "role_matters", "score": 12000, "body": "It depends on the job, but most messages labeled urgent are just poor planning wearing a hat."},
            {"author": "manager_problem", "score": 9700, "body": "A workplace that relies on unpaid after-hours replies is understaffed, not efficient."},
            {"author": "one_exception", "score": 7900, "body": "I will answer once if something is genuinely burning. I will not train people to expect it every night."},
            {"author": "mute_is_health", "score": 6300, "body": "Muting work apps after hours improved my life more than any productivity advice ever did."},
        ],
    },
    {
        "subreddit": "WouldYouRather",
        "author": "gift_math",
        "score": 22600,
        "num_comments": 4300,
        "title": "Would you rather receive a thoughtful cheap gift or an expensive lazy one?",
        "source_url": "fallback://thoughtful-cheap-vs-expensive-lazy",
        "body": "",
        "comments": [
            {"author": "thought_counts", "score": 11300, "body": "Thoughtful and cheap. An expensive lazy gift still feels like someone outsourced caring."},
            {"author": "useful_wins", "score": 9500, "body": "I want useful. Price and thoughtfulness both lose if the gift is going straight into a drawer."},
            {"author": "expensive_is_fine", "score": 7800, "body": "Expensive lazy depends on how lazy. If it is something I actually wanted, I will survive the lack of poetry."},
            {"author": "pressure_problem", "score": 6200, "body": "Thoughtful gifts are lovely, but sometimes people overthink them and create pressure around a normal birthday."},
            {"author": "listen_once", "score": 4800, "body": "The best gifts prove someone listened once. That does not have to cost much."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "phone_table",
        "score": 31100,
        "num_comments": 6900,
        "title": "Is it rude to put your phone on the table during dinner?",
        "source_url": "fallback://phone-on-table-dinner",
        "body": "",
        "comments": [
            {"author": "attention_signal", "score": 15700, "body": "It is not the phone itself. It is the signal that this conversation can be interrupted at any second."},
            {"author": "face_down_rule", "score": 13200, "body": "Face down is fine. Screen up lighting up every minute feels like a third person at the table."},
            {"author": "parent_exception", "score": 10600, "body": "If you have kids or someone sick, keep it nearby. Otherwise the pasta does not need your notifications."},
            {"author": "habit_problem", "score": 8600, "body": "Most people do it without thinking. That is exactly why it feels rude."},
            {"author": "same_energy", "score": 6900, "body": "If everyone has their phone out, fine. If one person is trying to connect and the other is scrolling, not fine."},
        ],
    },
    {
        "subreddit": "NoStupidQuestions",
        "author": "invite_rules",
        "score": 25800,
        "num_comments": 5600,
        "title": "Is it weird to invite yourself to plans you heard about?",
        "source_url": "fallback://invite-yourself-plans",
        "body": "",
        "comments": [
            {"author": "read_the_room", "score": 13400, "body": "Usually yes. If they wanted you there, the invitation would have made a stop at your phone."},
            {"author": "soft_ask", "score": 10900, "body": "There is a difference between inviting yourself and saying it sounds fun. Let them choose the next sentence."},
            {"author": "close_friend_rule", "score": 8700, "body": "With close friends it can be normal. With coworkers or acquaintances, it gets uncomfortable fast."},
            {"author": "budget_matters", "score": 7200, "body": "Some plans have reservations, tickets, cars, or budgets. People forget logistics are part of invitations."},
            {"author": "honesty_needed", "score": 5700, "body": "If people keep discussing plans in front of someone they are excluding, they are also being weird."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "coffee_debate",
        "score": 21900,
        "num_comments": 4800,
        "title": "What small workplace habit makes everyone secretly annoyed?",
        "source_url": "fallback://small-workplace-habit-annoyed",
        "body": "",
        "comments": [
            {"author": "meeting_creep", "score": 11200, "body": "Turning every quick question into a meeting. Some people treat calendars like a weapon."},
            {"author": "microwave_fish", "score": 9400, "body": "Heating food that takes over the whole office. Your lunch should not become everyone's atmosphere."},
            {"author": "reply_all_again", "score": 8200, "body": "Replying all with 'thanks.' Now sixty people know you are polite and bad at email."},
            {"author": "last_minute_task", "score": 6600, "body": "Dropping work at the end of the day and pretending it appeared naturally."},
            {"author": "loud_calls", "score": 5100, "body": "Taking loud calls in shared spaces. We are all now unwilling stakeholders in your update."},
        ],
    },
    {
        "subreddit": "hypotheticalsituation",
        "author": "money_friend",
        "score": 26600,
        "num_comments": 5400,
        "title": "Would you lend money to a friend who still owes other people?",
        "source_url": "fallback://lend-money-friend-owes",
        "body": "",
        "comments": [
            {"author": "donation_rule", "score": 13900, "body": "Only lend money you are emotionally ready to never see again. Otherwise you are buying resentment."},
            {"author": "pattern_is_answer", "score": 11400, "body": "If they owe multiple people, that is not bad luck anymore. That is a system."},
            {"author": "help_without_cash", "score": 9100, "body": "I might buy groceries or pay a bill directly. I would not hand over cash and hope."},
            {"author": "friendship_risk", "score": 7600, "body": "Money changes the relationship immediately. Suddenly every coffee they buy becomes evidence."},
            {"author": "small_once", "score": 5800, "body": "A small one-time emergency, maybe. A repeated pattern, no."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "group_chat",
        "score": 29300,
        "num_comments": 6300,
        "title": "What makes a group chat instantly annoying?",
        "source_url": "fallback://group-chat-annoying",
        "body": "",
        "comments": [
            {"author": "voice_note_novel", "score": 15100, "body": "Five-minute voice notes with no warning. I did not subscribe to an audio book."},
            {"author": "private_argument", "score": 12300, "body": "Two people having a private argument in front of everyone. Take the emotional tennis match elsewhere."},
            {"author": "reaction_spam", "score": 9700, "body": "Reacting to every single message. At some point the notifications become confetti nobody asked for."},
            {"author": "plan_restart", "score": 7900, "body": "Changing plans after everyone already agreed. The chat becomes a scheduling escape room."},
            {"author": "too_many_memes", "score": 6200, "body": "Memes are fine. Fifty in a row during work hours is a hostage situation."},
        ],
    },
    {
        "subreddit": "NoStupidQuestions",
        "author": "family_visit",
        "score": 24700,
        "num_comments": 5100,
        "title": "Is it rude for family to show up without calling first?",
        "source_url": "fallback://family-show-up-without-calling",
        "body": "",
        "comments": [
            {"author": "doorbell_boundary", "score": 12800, "body": "Family is not a free pass to ignore doors, schedules, or pants."},
            {"author": "depends_on_house", "score": 10400, "body": "Some families live like that and love it. The problem is assuming everyone else does too."},
            {"author": "call_first", "score": 8600, "body": "A text takes ten seconds. Surprise visits are only cute when everyone involved enjoys surprises."},
            {"author": "emergency_exception", "score": 7000, "body": "Emergencies are different. Bored on a Sunday is not an emergency."},
            {"author": "host_mode", "score": 5500, "body": "People underestimate how stressful it is to become a host with zero warning."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "line_rules",
        "score": 30400,
        "num_comments": 6700,
        "title": "What everyday behavior makes you lose respect for someone?",
        "source_url": "fallback://everyday-lose-respect",
        "body": "",
        "comments": [
            {"author": "rude_to_staff", "score": 16600, "body": "Being rude to service workers. It is the fastest personality test in public."},
            {"author": "never_apologizes", "score": 13500, "body": "People who cannot say sorry without building a defense case around it."},
            {"author": "litter_logic", "score": 10800, "body": "Littering when a bin is nearby. It tells me convenience beats basic decency for them."},
            {"author": "interrupt_machine", "score": 8300, "body": "Constantly interrupting and then saying they are just excited. Everyone else is also having thoughts."},
            {"author": "cheap_with_others", "score": 6800, "body": "Being generous with themselves and cheap when it is someone else's turn."},
        ],
    },
    {
        "subreddit": "WouldYouRather",
        "author": "privacy_trade",
        "score": 23900,
        "num_comments": 4900,
        "title": "Would you rather have free food forever or free rent forever?",
        "source_url": "fallback://free-food-or-rent",
        "body": "",
        "comments": [
            {"author": "rent_obviously", "score": 12600, "body": "Free rent. Food is expensive, but rent is the boss level."},
            {"author": "food_freedom", "score": 10100, "body": "Free food means never planning meals again. That is more daily happiness than people admit."},
            {"author": "city_answer", "score": 8400, "body": "In a big city this is not a question. Free rent changes your entire life."},
            {"author": "health_angle", "score": 6800, "body": "Free food depends on what food. Free rent has no hidden nutrition problem."},
            {"author": "both_are_traps", "score": 5200, "body": "Free anything forever sounds like there is a cursed terms and conditions page somewhere."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "social_battery",
        "score": 22100,
        "num_comments": 4700,
        "title": "Is cancelling plans because you are tired a valid reason?",
        "source_url": "fallback://cancel-plans-tired",
        "body": "",
        "comments": [
            {"author": "valid_but_timing", "score": 11700, "body": "Valid, but timing matters. Canceling three hours before is different from canceling when someone is already driving."},
            {"author": "pattern_matters", "score": 9300, "body": "Once is human. Every time means you like the idea of plans more than actual plans."},
            {"author": "honesty_wins", "score": 7800, "body": "I would rather hear 'I'm exhausted' than get a fake excuse with plot holes."},
            {"author": "respect_effort", "score": 6400, "body": "If someone cleaned, cooked, booked, or traveled for it, your tiredness is not the only factor."},
            {"author": "reschedule_real", "score": 5000, "body": "Canceling is fine if you actually reschedule. Otherwise it feels like a soft goodbye."},
        ],
    },
    {
        "subreddit": "NoStupidQuestions",
        "author": "borrow_rules",
        "score": 21600,
        "num_comments": 4400,
        "title": "Is it rude to ask for borrowed money back?",
        "source_url": "fallback://ask-borrowed-money-back",
        "body": "",
        "comments": [
            {"author": "your_money", "score": 11200, "body": "No. The rude part was making you ask for money they already agreed to return."},
            {"author": "clear_date", "score": 9100, "body": "Always set a date when you lend it. Vague repayment turns into awkward friendship fog."},
            {"author": "small_claims", "score": 7600, "body": "People act offended over being reminded, but they were not offended when they needed help."},
            {"author": "never_lend", "score": 6100, "body": "This is why I do not lend money. I either gift it or say no."},
            {"author": "calm_text", "score": 4800, "body": "A calm text is enough. If they make it dramatic, that tells you something useful."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "guest_rules",
        "score": 25400,
        "num_comments": 5300,
        "title": "What house guest behavior is an instant red flag?",
        "source_url": "fallback://house-guest-red-flag",
        "body": "",
        "comments": [
            {"author": "fridge_raider", "score": 13200, "body": "Opening the fridge without asking. That is not confidence, that is indoor trespassing."},
            {"author": "no_cleanup", "score": 10800, "body": "Leaving dishes, cups, and wrappers everywhere like the host won a cleaning internship."},
            {"author": "overstay_clock", "score": 8900, "body": "Not knowing when to leave. A good guest can read the room before the room starts begging."},
            {"author": "plus_one_surprise", "score": 7200, "body": "Bringing someone extra without asking. My home is not an open invite link."},
            {"author": "bathroom_mystery", "score": 5700, "body": "Leaving the bathroom worse than they found it. That one is impossible to unlearn about a person."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "dating_text",
        "score": 28100,
        "num_comments": 6000,
        "title": "What texting habit is a dating red flag?",
        "source_url": "fallback://dating-texting-red-flag",
        "body": "",
        "comments": [
            {"author": "hot_cold", "score": 14800, "body": "Being intense for two days and then disappearing for a week. That is not mystery, that is instability."},
            {"author": "only_late_night", "score": 12100, "body": "Only texting after 11 PM. At that point I am not a person, I am a notification option."},
            {"author": "question_vacuum", "score": 9900, "body": "Never asking questions back. It starts feeling like you are interviewing someone for a role they do not want."},
            {"author": "angry_delay", "score": 7900, "body": "Getting mad if you do not reply fast. That is not romance, that is customer service energy."},
            {"author": "dry_but_online", "score": 6200, "body": "Dry replies while constantly posting. Nobody is too busy, they are just allocating attention."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "friendship_meter",
        "score": 23700,
        "num_comments": 5000,
        "title": "What makes a friendship start feeling one-sided?",
        "source_url": "fallback://friendship-one-sided",
        "body": "",
        "comments": [
            {"author": "always_initiating", "score": 12600, "body": "When you stop texting first and the friendship quietly disappears."},
            {"author": "therapy_friend", "score": 10300, "body": "They only call when something is wrong. You become emotional tech support."},
            {"author": "no_questions", "score": 8400, "body": "They know every update about themselves and nothing about your life."},
            {"author": "convenience_only", "score": 6800, "body": "They are available when they need a favor, but suddenly booked when you need support."},
            {"author": "celebrate_gap", "score": 5400, "body": "They vent to you about losses but do not show up for your wins."},
        ],
    },
    {
        "subreddit": "NoStupidQuestions",
        "author": "neighbor_noise",
        "score": 20900,
        "num_comments": 4200,
        "title": "Is it petty to complain about loud neighbors?",
        "source_url": "fallback://complain-loud-neighbors",
        "body": "",
        "comments": [
            {"author": "sleep_is_basic", "score": 10900, "body": "Sleep is not a luxury request. If they are loud late at night, complaining is reasonable."},
            {"author": "talk_once", "score": 9000, "body": "Talk to them once if it feels safe. Some people truly do not realize how sound travels."},
            {"author": "not_every_noise", "score": 7400, "body": "Apartment living means some noise. It does not mean daily concerts through the wall."},
            {"author": "document_it", "score": 5900, "body": "If it is constant, document it. Vague complaints are easy to dismiss."},
            {"author": "petty_line", "score": 4600, "body": "Petty is complaining about footsteps at 2 PM. Not petty is bass at midnight."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "restaurant_rules",
        "score": 26900,
        "num_comments": 5800,
        "title": "What restaurant behavior tells you someone is hard to be around?",
        "source_url": "fallback://restaurant-hard-to-be-around",
        "body": "",
        "comments": [
            {"author": "server_test", "score": 14400, "body": "How they talk to the server. That tells you how they act when they think there are no consequences."},
            {"author": "order_drama", "score": 11600, "body": "Changing the order five times and acting like the staff created the confusion."},
            {"author": "tip_fight", "score": 9300, "body": "Starting a loud moral debate about tipping at the table. Nobody came to dinner for a panel discussion."},
            {"author": "send_back_serial", "score": 7600, "body": "Sending food back repeatedly over tiny issues. One problem is normal, a pattern is a personality."},
            {"author": "phone_loud", "score": 5900, "body": "Taking calls on speaker. Somehow their conversation becomes the appetizer for everyone."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "family_money",
        "score": 23200,
        "num_comments": 5100,
        "title": "Is it wrong to refuse lending money to family?",
        "source_url": "fallback://refuse-lending-family-money",
        "body": "",
        "comments": [
            {"author": "family_not_bank", "score": 12100, "body": "No. Being related does not turn you into a bank branch with feelings."},
            {"author": "gift_or_no", "score": 9800, "body": "If I cannot afford to gift it, I cannot afford to lend it. Family pressure does not change math."},
            {"author": "history_matters", "score": 7900, "body": "It depends on their history. Some people need help once. Some people turn help into a business model."},
            {"author": "boundary_guilt", "score": 6400, "body": "The guilt is usually the strategy. A fair request can survive a respectful no."},
            {"author": "non_cash_help", "score": 5000, "body": "You can help with groceries, forms, rides, or job leads without handing over money."},
        ],
    },
    {
        "subreddit": "NoStupidQuestions",
        "author": "apology_rules",
        "score": 21400,
        "num_comments": 4300,
        "title": "Is an apology real if someone keeps explaining why they did it?",
        "source_url": "fallback://apology-with-explaining",
        "body": "",
        "comments": [
            {"author": "explain_later", "score": 11200, "body": "Explanation can come after accountability. If it replaces accountability, it is just a press release."},
            {"author": "intent_vs_impact", "score": 9100, "body": "Intent matters, but impact is why the apology exists in the first place."},
            {"author": "sorry_but", "score": 7600, "body": "The word 'but' after sorry usually cancels the transaction."},
            {"author": "context_helps", "score": 6100, "body": "Sometimes context helps prevent the same mistake. It just should not sound like a courtroom defense."},
            {"author": "changed_behavior", "score": 4800, "body": "The real apology is changed behavior. The speech is just the trailer."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "social_rules",
        "score": 29800,
        "num_comments": 6500,
        "title": "What is rude but people pretend is just being honest?",
        "source_url": "fallback://rude-pretend-honest",
        "body": "",
        "comments": [
            {"author": "brutal_branding", "score": 15800, "body": "Calling cruelty honesty. If you enjoy the damage, truth is not the main point."},
            {"author": "unsolicited_opinion", "score": 12900, "body": "Giving harsh opinions nobody asked for. Honesty does not mean narrating every thought that walks by."},
            {"author": "just_joking", "score": 10200, "body": "Saying something mean and hiding behind 'just joking' when it lands badly."},
            {"author": "body_comments", "score": 8300, "body": "Commenting on someone's body and acting like concern makes it polite."},
            {"author": "timing_matters", "score": 6600, "body": "Truth at the wrong time, in the wrong tone, to the wrong audience can still be rude."},
        ],
    },
    {
        "subreddit": "WouldYouRather",
        "author": "social_choice",
        "score": 22300,
        "num_comments": 4700,
        "title": "Would you rather always be early or always be exactly on time?",
        "source_url": "fallback://early-or-on-time",
        "body": "",
        "comments": [
            {"author": "on_time_wins", "score": 11700, "body": "Exactly on time. Being early sounds polite until you are awkwardly waiting outside someone's house."},
            {"author": "early_buffer", "score": 9400, "body": "Early. I need a stress buffer between travel and pretending to be normal."},
            {"author": "host_problem", "score": 7800, "body": "Being early to someone's home is not always helpful. Sometimes the host is still hiding laundry."},
            {"author": "work_answer", "score": 6200, "body": "For work, early. For social plans, exactly on time. Context changes everything."},
            {"author": "late_people", "score": 5000, "body": "Either one sounds better than being the friend who treats time as a rumor."},
        ],
    },
    {
        "subreddit": "AskReddit",
        "author": "shopping_cart",
        "score": 25100,
        "num_comments": 5400,
        "title": "What shopping habit instantly annoys you?",
        "source_url": "fallback://shopping-habit-annoys",
        "body": "",
        "comments": [
            {"author": "aisle_parking", "score": 13200, "body": "Parking the cart sideways across the aisle like they are protecting a crime scene."},
            {"author": "checkout_surprise", "score": 10800, "body": "Waiting until everything is scanned to start looking for payment. The total was not a plot twist."},
            {"author": "line_cutting", "score": 8900, "body": "Pretending not to see the line. Everyone saw you see it."},
            {"author": "speakerphone_store", "score": 7200, "body": "Speakerphone conversations in a store. Now we are all shopping with your cousin."},
            {"author": "freezer_door", "score": 5600, "body": "Leaving freezer doors open while deciding. The ice cream is not part of your brainstorming session."},
        ],
    },
]

SAMPLE_POST = SAMPLE_POSTS[0]

KOKORO_PIPELINE = None
KOKORO_VOICES = ["af_heart", "am_adam", "af_bella", "am_michael"]
EDGE_VOICES = [
    "en-US-AndrewNeural",
    "en-US-EmmaNeural",
    "en-US-BrianNeural",
    "en-US-AvaNeural",
]

# Per-beat prosody: segment kind -> (rate, pitch). Replaces the old flat +16% speed-up
# that made every segment sound rushed and robotic. Delivery now tracks the moment.
EDGE_BEAT_PROSODY = {
    "hook": ("-2%", "+1Hz"),            # post title: slower, draws the viewer in
    "conversational": ("+3%", "+0Hz"),  # comments: natural, like a real person talking
    "invite": ("+5%", "+2Hz"),          # CTA: upbeat, a nudge to engage
    "calm": ("+0%", "+0Hz"),
}
KIND_TO_BEAT = {"post": "hook", "comment": "conversational", "cta": "invite"}

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
    return not any(term_in_text(term, text) for term in UNSAFE_TERMS)


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


@lru_cache(maxsize=1)
def curated_posts():
    try:
        data = json.loads(CURATED_POSTS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as exc:
        print(f"Ignoring curated posts file: {exc}")
        return []
    posts = data.get("posts", data if isinstance(data, list) else [])
    return [post for post in posts if isinstance(post, dict) and post.get("title") and post.get("comments")]


def all_sample_posts():
    return SAMPLE_POSTS + curated_posts()


def infer_bucket(post):
    explicit = post.get("bucket")
    if explicit:
        return explicit
    title = (post.get("title") or "").lower()
    for bucket, keywords in BUCKET_KEYWORDS.items():
        if any(term_in_text(keyword, title) for keyword in keywords):
            return bucket
    return "etiquette"


def procedural_post(bucket, index, posted_sources):
    spec = PROCEDURAL_ANGLES.get(bucket) or PROCEDURAL_ANGLES["etiquette"]
    actions = spec["actions"]
    contexts = spec["contexts"]
    frames = QUESTION_FRAMES
    total = len(actions) * len(contexts) * len(frames)

    for offset in range(total * 20):
        seed = index + offset
        action = actions[(seed // len(frames)) % len(actions)]
        context = contexts[(seed // (len(frames) * len(actions))) % len(contexts)]
        if bucket == "would_you_rather":
            title = f"Would you rather {action} {context}?"
        else:
            frame = frames[seed % len(frames)]
            title = frame.format(action=action, context=context)
        source_url = f"procedural://{bucket}/{seed}"
        if source_url in posted_sources:
            continue
        comments = PROCEDURAL_COMMENTS.get(bucket, PROCEDURAL_COMMENTS["etiquette"])
        return {
            "bucket": bucket,
            "subreddit": "WouldYouRather" if bucket == "would_you_rather" else "AskReddit",
            "author": f"{bucket}_angle",
            "score": 18000 + ((seed * 7919) % 26000),
            "num_comments": 3000 + ((seed * 3571) % 7000),
            "title": title,
            "source_url": source_url,
            "body": "",
            "comments": [
                {
                    "author": f"{bucket}_take_{i + 1}",
                    "score": 5000 + (((seed + 11) * (i + 3) * 997) % 15000),
                    "body": comments[(seed + i) % len(comments)],
                }
                for i in range(min(MAX_COMMENTS, len(comments)))
            ],
        }
    return None


def fallback_post():
    raw_index = os.getenv("FALLBACK_POST_INDEX") or os.getenv("GITHUB_RUN_NUMBER") or os.getenv("GITHUB_RUN_ID")
    index = int(raw_index) if raw_index and raw_index.isdigit() else int(time.time() // 3600)
    posts = all_sample_posts()
    posted_sources = load_posted_sources()
    desired_bucket = os.getenv("CONTENT_BUCKET") or BUCKET_ORDER[index % len(BUCKET_ORDER)]

    fresh_bucket = [post for post in posts if post.get("source_url") not in posted_sources and infer_bucket(post) == desired_bucket]
    if fresh_bucket:
        return json.loads(json.dumps(fresh_bucket[index % len(fresh_bucket)]))

    generated = procedural_post(desired_bucket, index, posted_sources)
    if generated:
        return json.loads(json.dumps(generated))

    groups = [
        [post for post in posts if post.get("source_url") not in posted_sources],
        [post for post in posts if infer_bucket(post) == desired_bucket],
        posts,
    ]
    for group in groups:
        if group:
            return json.loads(json.dumps(group[index % len(group)]))
    return json.loads(json.dumps(SAMPLE_POST))


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


def make_voice(text, audio_path, index, beat="calm"):
    if edge_voice(text, audio_path, index, beat):
        return
    if kokoro_voice(text, audio_path, index):
        return

    tts = shutil.which("espeak-ng")
    if not tts:
        raise RuntimeError("No local TTS found. Install edge-tts or espeak-ng.")
    voice = "en-us+m3" if index % 2 else "en-us+f3"
    subprocess.run([tts, "-v", voice, "-s", "155", "-w", str(audio_path), text], check=True)


def edge_voice(text, audio_path, index, beat="calm"):
    if not DEPS.exists():
        return False

    try:
        sys.path.insert(0, str(DEPS))
        import edge_tts

        voice = EDGE_VOICES[index % len(EDGE_VOICES)]
        rate, pitch = EDGE_BEAT_PROSODY.get(beat, EDGE_BEAT_PROSODY["calm"])

        async def synthesize():
            communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
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
            beat = KIND_TO_BEAT.get(segment.get("kind"), "calm")
            make_voice(segment["voice"], audio_path, index, beat)
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
