#!/usr/bin/env bash
# Bootstrap launcher for ai-news-digest MCP server.
#
# Claude Code plugin install only fetches the repo and reads plugin.json —
# it does not run pip install. This launcher creates a dedicated venv
# under ${CLAUDE_PLUGIN_DATA}/venv on first run and installs the package
# there in editable mode. Subsequent runs skip straight to the exec.
#
# Using a venv (rather than --user with --break-system-packages) keeps
# the install fully isolated from the user's system / Homebrew Python
# and sidesteps PEP 668 entirely.
#
# Requires Python 3.12+ on PATH (as python3.12, python3, or python).

set -euo pipefail

# Self-locate the plugin root (this script's dir, then ..)
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Pick the highest available Python; verify >= 3.12
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

if ! "$PYTHON" -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" 2>/dev/null; then
  echo "ai-news-digest: requires Python 3.12+ (found $("$PYTHON" --version 2>&1))." >&2
  exit 1
fi

# Dedicated venv lives in ${CLAUDE_PLUGIN_DATA}, which Claude Code persists
# across plugin updates (per plugins-reference docs). Fallback to a path
# inside the plugin dir when this script is run outside Claude Code
# (e.g. for local debugging).
DATA_DIR="${CLAUDE_PLUGIN_DATA:-${PLUGIN_DIR}/.local}"
VENV_DIR="${DATA_DIR}/venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
MARKER="${VENV_DIR}/.installed-from"

# Create venv if missing (first run, or user deleted it)
if [ ! -x "${VENV_PYTHON}" ]; then
  echo "ai-news-digest: creating plugin venv at ${VENV_DIR}..." >&2
  mkdir -p "${DATA_DIR}"
  "$PYTHON" -m venv "${VENV_DIR}"
fi

# (Re)install when the venv has never been installed from the current
# PLUGIN_DIR, or when ai_news_digest is missing entirely. The marker file
# detects plugin updates that move ${CLAUDE_PLUGIN_ROOT} to a new install
# dir (the previous editable install would otherwise go stale).
if [ ! -f "${MARKER}" ] || [ "$(cat "${MARKER}")" != "${PLUGIN_DIR}" ] || \
   ! "${VENV_PYTHON}" -c "import ai_news_digest" >/dev/null 2>&1; then
  echo "ai-news-digest: installing/updating Python deps in plugin venv..." >&2
  "${VENV_PYTHON}" -m pip install --quiet --upgrade pip
  "${VENV_PYTHON}" -m pip install --quiet -e "${PLUGIN_DIR}[mcp]"
  echo "${PLUGIN_DIR}" > "${MARKER}"
fi

# Exec the MCP server (stdio transport — handed to the Claude host)
exec "${VENV_PYTHON}" -m ai_news_digest.mcp_server
