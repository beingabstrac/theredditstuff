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

## Reddit API

Optional free credentials:

```bash
export REDDIT_CLIENT_ID="..."
export REDDIT_CLIENT_SECRET="..."
```

Without those, it uses sample content.
