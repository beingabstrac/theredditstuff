#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$PROJECT_DIR"
/Users/rishi/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 src/theredditstuff_reel.py
