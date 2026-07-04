#!/usr/bin/env python3
import base64
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_FILE = ROOT / "src" / "theredditstuff_reel.py"
CURATED_FILE = ROOT / "data" / "curated_posts.json"
POSTED_FILE = ROOT / "data" / "posted_sources.json"
REPORT_FILE = ROOT / "outputs" / "autopilot_report.md"


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path} is invalid JSON: {exc}") from exc


def source_urls_from_code():
    text = SRC_FILE.read_text(encoding="utf-8")
    return set(re.findall(r'"source_url":\s*"([^"]+)"', text))


def curated_posts():
    data = load_json(CURATED_FILE, {"posts": []})
    posts = data.get("posts", data if isinstance(data, list) else [])
    return [post for post in posts if isinstance(post, dict) and post.get("source_url")]


def posted_items():
    data = load_json(POSTED_FILE, {"posted": []})
    return [item for item in data.get("posted", []) if item.get("source_url")]


def cloudinary_config():
    cloudinary_url = os.getenv("CLOUDINARY_URL", "")
    if cloudinary_url:
        parsed = urllib.parse.urlparse(cloudinary_url)
        return parsed.hostname, parsed.username, parsed.password
    return os.getenv("CLOUDINARY_CLOUD_NAME"), os.getenv("CLOUDINARY_API_KEY"), os.getenv("CLOUDINARY_API_SECRET")


def cloudinary_summary():
    cloud_name, api_key, api_secret = cloudinary_config()
    if not cloud_name or not api_key or not api_secret:
        return {"configured": False}
    if os.getenv("SKIP_CLOUDINARY_CHECK") == "1":
        return {"configured": True, "skipped": True}

    auth = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
    params = urllib.parse.urlencode({"prefix": "theredditstuff/", "max_results": "100"})
    req = urllib.request.Request(
        f"https://api.cloudinary.com/v1_1/{cloud_name}/resources/video/upload?{params}",
        headers={"Authorization": f"Basic {auth}"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    resources = data.get("resources", [])
    return {
        "configured": True,
        "count": len(resources),
        "bytes": sum(item.get("bytes", 0) for item in resources),
        "has_more": bool(data.get("next_cursor")),
    }


def hours_since_last_queue(items):
    if not items:
        return None
    newest = items[0].get("posted_at")
    if not newest:
        return None
    dt = datetime.fromisoformat(newest.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600


def main():
    posts_per_day = int(os.getenv("POSTS_PER_DAY", "5"))
    min_runway_days = int(os.getenv("MIN_CONTENT_RUNWAY_DAYS", "14"))
    max_hours_without_queue = int(os.getenv("MAX_HOURS_WITHOUT_QUEUE", "40"))

    curated = curated_posts()
    code_sources = source_urls_from_code()
    curated_sources = {post["source_url"] for post in curated}
    total_sources = code_sources | curated_sources
    posted = posted_items()
    posted_sources = {item["source_url"] for item in posted}
    remaining_sources = total_sources - posted_sources
    runway_days = len(remaining_sources) / max(posts_per_day, 1)
    last_queue_hours = hours_since_last_queue(posted)

    missing = [name for name in ["BUFFER_API_KEY", "BUFFER_INSTAGRAM_CHANNEL_ID"] if not os.getenv(name)]
    cloud_name, cloud_key, cloud_secret = cloudinary_config()
    if not (cloud_name and cloud_key and cloud_secret):
        missing.append("CLOUDINARY_URL or CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET")

    problems = []
    warnings = []
    if missing:
        problems.append(f"Missing secrets/env: {', '.join(missing)}")
    if len(curated) < 100:
        warnings.append(f"Curated bank is small: {len(curated)}")
    if runway_days < min_runway_days:
        problems.append(f"Content runway is low: {runway_days:.1f} days")
    if last_queue_hours is None:
        warnings.append("No queue history yet")
    elif last_queue_hours > max_hours_without_queue:
        problems.append(f"No new queued reel in {last_queue_hours:.1f} hours")

    try:
        cloudinary = cloudinary_summary()
    except Exception as exc:
        cloudinary = {"configured": True, "error": str(exc)}
        warnings.append(f"Cloudinary check failed: {exc}")

    report = [
        "# Autopilot Health",
        "",
        f"- Status: {'FAIL' if problems else 'OK'}",
        f"- Posts/day target: {posts_per_day}",
        f"- Total source bank: {len(total_sources)}",
        f"- Curated source bank: {len(curated)}",
        f"- Posted/queued history: {len(posted_sources)}",
        f"- Remaining before repeats: {len(remaining_sources)}",
        f"- Estimated runway: {runway_days:.1f} days",
        f"- Last queued: {'never' if last_queue_hours is None else f'{last_queue_hours:.1f} hours ago'}",
        f"- Cloudinary: {cloudinary}",
        "",
        "## Problems",
        *(f"- {item}" for item in (problems or ["None"])),
        "",
        "## Warnings",
        *(f"- {item}" for item in (warnings or ["None"])),
        "",
    ]
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))

    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        Path(summary).write_text("\n".join(report), encoding="utf-8")

    if problems:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
