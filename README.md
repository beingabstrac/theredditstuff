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

## Real Reddit Usernames

For real post/comment usernames, use free Reddit API credentials:

```bash
export REDDIT_CLIENT_ID="..."
export REDDIT_CLIENT_SECRET="..."
```

Without those, the script tries public Reddit JSON. If Reddit blocks it, it uses sample content.

Custom source pool:

```bash
SUBREDDITS=AskReddit,hypotheticalsituation,WouldYouRather ./scripts/render.sh
```
