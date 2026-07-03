# theredditstuff Reel MVP

Free local pipeline for making short Reddit-style reels for `@theredditstuff`.

## What it does

- Picks shareable Reddit posts: relatable, debatable, easy to understand.
- Shows each post/comment on a Reddit-orange background.
- Reads text aloud with free local TTS.
- Uses lightweight free local `espeak-ng` by default.
- Can use Kokoro only if explicitly enabled with `USE_KOKORO=1`.
- Renders vertical MP4 with `ffmpeg`.
- Deletes temporary render files automatically.

## Run

```bash
./scripts/render.sh
```

Final output kept:

```text
outputs/theredditstuff_mvp.mp4
```

## Automation

GitHub Actions can render and queue 3 Instagram posts per day through Buffer.

Schedule:

```text
10:00, 15:00, 20:00 IST
```

Required GitHub Secrets:

```text
BUFFER_API_KEY
BUFFER_INSTAGRAM_CHANNEL_ID
CLOUDINARY_URL
```

Cloudinary is used only to host the MP4 publicly so Buffer can fetch it. Free plan is enough for MVP.

The action keeps only a small duplicate-history file:

```text
data/posted_sources.json
```

## Real Reddit Usernames

For real post/comment usernames, use free Reddit API credentials:

```bash
export REDDIT_CLIENT_ID="..."
export REDDIT_CLIENT_SECRET="..."
```

Without those, the script uses Reddit RSS feeds. If RSS comments are rate-limited, it uses safe sample content.

Custom source pool:

```bash
SUBREDDITS=AskReddit,hypotheticalsituation,WouldYouRather ./scripts/render.sh
```
