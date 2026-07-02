# AskReddit Reel MVP

Free local pipeline for making short AskReddit-style reels.

## What it does

- Picks shareable AskReddit posts: relatable, debatable, easy to understand.
- Shows each post/comment on a Reddit-orange background.
- Reads text aloud with free local TTS.
- Alternates female/male Kokoro voices when available.
- Falls back to `espeak-ng`.
- Renders vertical MP4 with `ffmpeg`.

## Run

```bash
./scripts/render.sh
```

Output:

```text
outputs/askreddit_mvp.mp4
```

## Reddit API

Optional free credentials:

```bash
export REDDIT_CLIENT_ID="..."
export REDDIT_CLIENT_SECRET="..."
```

Without those, it uses sample content.
