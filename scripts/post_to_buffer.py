#!/usr/bin/env python3
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIDEO_PATH = ROOT / "outputs" / "theredditstuff_mvp.mp4"
STORY_PATH = ROOT / "outputs" / "theredditstuff_storyboard.json"
POSTED_SOURCES_FILE = Path(os.getenv("POSTED_SOURCES_FILE", ROOT / "data" / "posted_sources.json"))


def require_env(name):
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def load_story():
    return json.loads(STORY_PATH.read_text(encoding="utf-8"))


def caption_for_story(story):
    post = story["post"]
    subreddit = post.get("subreddit", "AskReddit")
    title = post["title"].strip()
    cta = story["segments"][-1]["text"].replace("\n", " ")
    tags = "#theredditstuff #askreddit #redditstories #reels #shorts"
    return f"{title}\n\n{cta}\n\nr/{subreddit}\n\n{tags}"


def multipart_body(fields, files):
    boundary = f"----theredditstuff{int(time.time())}"
    chunks = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(str(value).encode())
        chunks.append(b"\r\n")
    for name, path in files.items():
        data = Path(path).read_bytes()
        chunks.append(f"--{boundary}\r\n".encode())
        header = (
            f'Content-Disposition: form-data; name="{name}"; filename="{Path(path).name}"\r\n'
            "Content-Type: video/mp4\r\n\r\n"
        )
        chunks.append(header.encode())
        chunks.append(data)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return boundary, b"".join(chunks)


def cloudinary_config():
    cloudinary_url = os.getenv("CLOUDINARY_URL", "")
    if cloudinary_url:
        parsed = urllib.parse.urlparse(cloudinary_url)
        return parsed.hostname, parsed.username, parsed.password
    return os.getenv("CLOUDINARY_CLOUD_NAME"), os.getenv("CLOUDINARY_API_KEY"), os.getenv("CLOUDINARY_API_SECRET")


def cloudinary_upload(video_path):
    cloud_name, api_key, api_secret = cloudinary_config()
    if not cloud_name or not api_key or not api_secret:
        raise RuntimeError("Set PUBLIC_VIDEO_URL or Cloudinary env vars for public MP4 hosting.")

    timestamp = str(int(time.time()))
    public_id = f"theredditstuff/{timestamp}"
    params = {"public_id": public_id, "timestamp": timestamp, "overwrite": "true"}
    signature_base = "&".join(f"{key}={params[key]}" for key in sorted(params))
    signature = hashlib.sha1(f"{signature_base}{api_secret}".encode()).hexdigest()
    fields = {**params, "api_key": api_key, "signature": signature}
    boundary, body = multipart_body(fields, {"file": video_path})
    req = urllib.request.Request(
        f"https://api.cloudinary.com/v1_1/{cloud_name}/video/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["secure_url"]


def public_video_url():
    return os.getenv("PUBLIC_VIDEO_URL") or cloudinary_upload(VIDEO_PATH)


def gql_string(value):
    return json.dumps(value)


def create_buffer_post(caption, video_url):
    api_key = require_env("BUFFER_API_KEY")
    channel_id = require_env("BUFFER_INSTAGRAM_CHANNEL_ID")
    mutation = f"""
    mutation {{
      createPost(input: {{
        channelId: {gql_string(channel_id)}
        text: {gql_string(caption)}
        metadata: {{
          instagram: {{
            type: reel
            shouldShareToFeed: true
            isAiGenerated: false
          }}
        }}
        schedulingType: automatic
        mode: addToQueue
        assets: [
          {{
            video: {{
              url: {gql_string(video_url)}
            }}
          }}
        ]
      }}) {{
        ... on PostActionSuccess {{
          post {{ id text }}
        }}
        ... on MutationError {{
          message
        }}
      }}
    }}
    """
    req = urllib.request.Request(
        "https://api.buffer.com/graphql",
        data=json.dumps({"query": mutation}).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Buffer HTTP {exc.code}: {body}") from exc
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    result = data.get("data", {}).get("createPost", {})
    if result.get("message"):
        message = result["message"]
        if os.getenv("IGNORE_QUEUE_FULL") == "1" and is_queue_full_error(message):
            print(json.dumps({"skipped": "queue_full", "message": message}, indent=2))
            return None
        raise RuntimeError(message)
    return result.get("post", {})


def is_queue_full_error(message):
    text = (message or "").lower()
    markers = ["queue", "limit", "maximum", "max", "scheduled posts", "10 posts"]
    return any(marker in text for marker in markers)


def mark_posted(story, buffer_post):
    post = story["post"]
    source_url = post.get("source_url")
    if not source_url:
        return
    try:
        data = json.loads(POSTED_SOURCES_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {"posted": []}
    existing = {item.get("source_url") for item in data.get("posted", [])}
    if source_url in existing:
        return
    data.setdefault("posted", []).insert(
        0,
        {
            "source_url": source_url,
            "title": post.get("title"),
            "buffer_post_id": buffer_post.get("id"),
            "posted_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    data["posted"] = data["posted"][:200]
    POSTED_SOURCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    POSTED_SOURCES_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main():
    if not VIDEO_PATH.exists():
        raise RuntimeError(f"Missing video: {VIDEO_PATH}")
    story = load_story()
    caption = caption_for_story(story)
    video_url = public_video_url()
    if os.getenv("DRY_RUN") == "1":
        print(json.dumps({"caption": caption, "video_url": video_url}, indent=2))
        return
    buffer_post = create_buffer_post(caption, video_url)
    if not buffer_post:
        return
    mark_posted(story, buffer_post)
    print(json.dumps({"buffer_post": buffer_post, "video_url": video_url}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"post_to_buffer failed: {exc}", file=sys.stderr)
        raise
