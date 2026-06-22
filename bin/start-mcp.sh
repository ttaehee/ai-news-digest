#!/usr/bin/env bash
# Bootstrap launcher for ai-news-digest MCP server.
#
# Claude Code plugin install only fetches the repo and reads plugin.json —
# it does not run pip install. This script bridges that gap: on first run
# it installs the Python deps from this plugin directory, then execs the
# stdio MCP server. Re-runs skip the install once the package is importable.
#
# Requires Python 3.12+ on PATH (as python3.12, python3, or python).

set -euo pipefail

# Self-locate the plugin root (this script's dir, then ..)
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Prefer python3.12 (pyproject's requires-python); fall back to python3 / python.
PYTHON=""
for candidate in python3.12 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "ai-news-digest: python not found on PATH. Install Python 3.12+ first." >&2
  exit 1
fi

# Verify version >= 3.12 (pyproject's requires-python).
if ! "$PYTHON" -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" 2>/dev/null; then
  echo "ai-news-digest: requires Python 3.12+ (found $("$PYTHON" --version 2>&1))." >&2
  exit 1
fi

# Lazy install: if ai_news_digest is not importable, pip install from the
# plugin dir with the mcp extra. --user avoids touching system site-packages.
if ! "$PYTHON" -c "import ai_news_digest" >/dev/null 2>&1; then
  echo "ai-news-digest: first-run install of Python deps (this only happens once)..." >&2
  "$PYTHON" -m pip install --quiet --user -e "${PLUGIN_DIR}[mcp]" >&2
fi

# Exec the MCP server (stdio transport — handed to the Claude host).
exec "$PYTHON" -m ai_news_digest.mcp_server
