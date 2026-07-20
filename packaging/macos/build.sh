#!/usr/bin/env bash
# Compatibility wrapper — real logic is packaging/macos/build.py
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec python3 "$ROOT/packaging/macos/build.py"
