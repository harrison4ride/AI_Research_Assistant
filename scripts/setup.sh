#!/usr/bin/env bash
# Set up everything the AI Research Assistant needs (details: INSTALL.md).
#
# Usage: ./scripts/setup.sh [--check] [--no-prompt]
#   --check      Only report which requirements are met. Installs nothing.
#   --no-prompt  Never ask questions (also the default when stdin is not a terminal).
#
# Steps: check uv and Node.js; install Python 3.11 and the backend packages
# (backend/.venv); install the frontend packages (frontend/node_modules);
# create .env from .env.example and validate its values; check the language
# model: the local Claude Code login (default), or an Anthropic API key, which
# it can store for you. Safe to re-run: an existing .env is never replaced.
#
# Written for bash 3.2, the version macOS ships.

set -euo pipefail

# CDPATH would make `cd` print the directory and corrupt ROOT.
ROOT="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." >/dev/null && pwd)"
ENV_FILE="$ROOT/.env"
VENV_PY="$ROOT/backend/.venv/bin/python"
NODE_REQUIREMENT="22.13 or later"
NODE_HELP="Install Node.js 22 LTS from https://nodejs.org, or run: brew install node (or: nvm install 22)"

usage() {
  sed -n '4,6p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

CHECK_ONLY=0
PROMPT=1
[ -t 0 ] || PROMPT=0
for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    --no-prompt) PROMPT=0 ;;
    -h | --help) usage; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; usage >&2; exit 2 ;;
  esac
done

if [ -t 1 ]; then
  BOLD=$'\033[1m' GREEN=$'\033[32m' YELLOW=$'\033[33m' RED=$'\033[31m' RESET=$'\033[0m'
else
  BOLD='' GREEN='' YELLOW='' RED='' RESET=''
fi
step() { printf '\n%s%s%s\n' "$BOLD" "$1" "$RESET"; }
ok() { printf '  %s✓%s %s\n' "$GREEN" "$RESET" "$1"; }
warn() { printf '  %s!%s %s\n' "$YELLOW" "$RESET" "$1"; }
fail() { printf '  %s✗%s %s\n' "$RED" "$RESET" "$1"; }

# Ask a yes/no question; the answer defaults to no.
confirm() {
  [ "$PROMPT" -eq 1 ] || return 1
  local reply
  read -r -p "  $1 [y/N] " reply || return 1
  case "$reply" in [yY] | [yY][eE][sS]) return 0 ;; *) return 1 ;; esac
}

# True if a Node.js version like "22.22.0" is 22.13 or later (PDF.js 6 needs
# >=22.13; Vite 8 alone would accept ^20.19 || >=22.12).
node_version_ok() {
  local major minor
  major="${1%%.*}"
  minor=0
  case "$1" in *.*) minor="${1#*.}"; minor="${minor%%.*}" ;; esac
  case "$major$minor" in *[!0-9]*) return 1 ;; esac
  if [ "$major" -eq 22 ]; then [ "$minor" -ge 13 ]; return; fi
  [ "$major" -gt 22 ]
}

# Run Python in the backend environment, from backend/ (where the app package lives).
backend_python() {
  (cd "$ROOT/backend" && "$VENV_PY" "$@")
}

# Load the settings exactly as the app does (same .env parser and validation),
# without importing the rest of the app, so nothing is created on disk.
# On failure, SETTINGS_ERROR holds the last lines of the error.
SETTINGS_ERROR=''
settings_valid() {
  local out
  if out="$(backend_python -c "from app.config import Settings; Settings()" 2>&1)"; then
    return 0
  fi
  # Drop pydantic's help-link lines and traceback underlines (^^^) so the
  # setting name and its allowed values are what remains.
  SETTINGS_ERROR="$(printf '%s\n' "$out" | grep -v -e 'errors.pydantic.dev' -e '^[[:space:]^~]*$' | tail -n 3 | sed 's/^/    /')"
  return 1
}

# Ask the app which LLM provider is configured and whether it is ready.
# Sets LLM_PROVIDER, LLM_LABEL, LLM_READY (yes/no) and LLM_HINT.
llm_status() {
  local info
  info="$(backend_python -c '
import asyncio
from app.config import get_settings
from app.services.llm import llm_status, model_label
ready, hint = asyncio.run(llm_status())
print("\t".join([get_settings().llm_provider, model_label(), "yes" if ready else "no", hint or ""]))
' 2>/dev/null)" || info=''
  IFS=$'\t' read -r LLM_PROVIDER LLM_LABEL LLM_READY LLM_HINT <<<"$info" || true
}

# True if the app will find Anthropic credentials: a key in .env or the shell,
# ANTHROPIC_AUTH_TOKEN, or an `ant auth login` profile (the app's own check).
credentials_found() {
  backend_python -c "import sys; from app.services.llm import credentials_available; sys.exit(0 if credentials_available() else 1)" >/dev/null 2>&1
}

# Earlier versions also read backend/.env; it is now ignored.
warn_backend_env() {
  if [ -f "$ROOT/backend/.env" ]; then
    warn "backend/.env is no longer read. Move its settings into .env in the project root."
  fi
}

missing=0

# --- 1. Tools -------------------------------------------------------------

step "1. Required tools"

if ! command -v uv >/dev/null 2>&1 && [ "$CHECK_ONLY" -eq 0 ] &&
  confirm "uv (the Python package manager) is not installed. Install it now? It goes in ~/.local/bin; no sudo needed."; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # The installer uses $UV_INSTALL_DIR, then $XDG_BIN_HOME, then ~/.local/bin.
  for dir in "$HOME/.local/bin" "${XDG_BIN_HOME:-}" "${UV_INSTALL_DIR:-}"; do
    if [ -n "$dir" ]; then PATH="$dir:$PATH"; fi
  done
  export PATH
fi
if ! command -v uv >/dev/null 2>&1; then
  fail "uv not found. Install it: curl -LsSf https://astral.sh/uv/install.sh | sh   (or: brew install uv)"
  missing=1
elif uv_version="$(uv --version 2>/dev/null | awk '{print $2}')" && [ -n "$uv_version" ]; then
  ok "uv $uv_version"
else
  fail "uv is on PATH but 'uv --version' failed. Reinstall uv: https://docs.astral.sh/uv/"
  missing=1
fi

if ! command -v node >/dev/null 2>&1; then
  fail "Node.js not found. $NODE_HELP"
  missing=1
elif node_version="$(node --version 2>/dev/null)" && [ -n "$node_version" ]; then
  node_version="${node_version#v}"
  if node_version_ok "$node_version"; then
    ok "Node.js $node_version"
  else
    fail "Node.js $node_version is not supported; the frontend (PDF.js 6) needs $NODE_REQUIREMENT. $NODE_HELP"
    missing=1
  fi
else
  fail "Node.js is on PATH but 'node --version' failed (a version manager with no version selected?). $NODE_HELP"
  missing=1
fi

if ! command -v npm >/dev/null 2>&1; then
  fail "npm not found. It ships with Node.js; reinstall Node.js."
  missing=1
elif npm_version="$(npm --version 2>/dev/null)" && [ -n "$npm_version" ]; then
  ok "npm $npm_version"
else
  fail "npm is on PATH but 'npm --version' failed; reinstall Node.js."
  missing=1
fi

if command -v make >/dev/null 2>&1; then
  ok "make (optional)"
else
  warn "make not found (optional). Use the plain commands in INSTALL.md instead of the make shortcuts."
fi

# --- Check-only mode: report and stop -------------------------------------

if [ "$CHECK_ONLY" -eq 1 ]; then
  step "2. Project setup"
  # Read-only checks: nothing below installs packages or creates files.
  backend_ok=0
  if ! command -v uv >/dev/null 2>&1; then
    fail "Backend packages not checked (uv missing)"
  elif (cd "$ROOT/backend" && uv sync --locked --check) >/dev/null 2>&1; then
    ok "Backend packages match backend/uv.lock"
    backend_ok=1
  else
    fail "Backend packages missing or out of date"
    missing=1
  fi
  if [ -d "$ROOT/frontend/node_modules" ] && (cd "$ROOT/frontend" && npm ls --depth=0) >/dev/null 2>&1; then
    ok "Frontend packages installed"
  else
    fail "Frontend packages missing or incomplete"
    missing=1
  fi
  if [ -f "$ENV_FILE" ]; then ok ".env exists"; else fail ".env missing"; missing=1; fi
  warn_backend_env
  if [ "$backend_ok" -eq 1 ]; then
    if settings_valid; then
      ok "Every .env value is valid"
    else
      fail "Invalid value in .env:"
      printf '%s\n' "$SETTINGS_ERROR"
      missing=1
    fi
    llm_status
    if [ "$LLM_READY" = "yes" ]; then
      ok "Summaries and Q&A ready: $LLM_LABEL"
    else
      warn "Summaries and Q&A unavailable (search, library, and upload still work). ${LLM_HINT:-Could not check the language model.}"
    fi
  fi
  echo
  if [ "$missing" -eq 0 ]; then echo "Everything required is in place."; else echo "Some requirements are missing; run ./scripts/setup.sh to install them."; fi
  exit "$missing"
fi

if [ "$missing" -ne 0 ]; then
  echo
  echo "Install the missing tools above, then run this script again."
  exit 1
fi

# --- 2. Packages ----------------------------------------------------------

step "2. Backend: Python 3.11 and packages (backend/.venv)"
# uv uses an installed Python 3.11 or downloads one (pinned in
# backend/.python-version), then installs the exact versions in backend/uv.lock.
(cd "$ROOT/backend" && uv sync --locked)
ok "Backend packages installed"

step "3. Frontend: packages (frontend/node_modules)"
# npm ci installs the exact versions in frontend/package-lock.json.
(cd "$ROOT/frontend" && npm ci --no-audit --no-fund)
ok "Frontend packages installed"

# --- 3. Configuration -----------------------------------------------------

step "4. Configuration (.env)"
if [ ! -e "$ENV_FILE" ]; then
  cp "$ROOT/.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE" # it will hold an API key
  ok "Created .env from .env.example"
elif [ -r "$ENV_FILE" ] && [ -w "$ENV_FILE" ]; then
  ok ".env already exists; leaving its values unchanged"
else
  fail ".env exists but you cannot read or write it. Check its owner and permissions: ls -l .env"
  exit 1
fi

warn_backend_env
if settings_valid; then
  ok "Every .env value is valid"
else
  fail "Invalid value in .env. Fix it and run this script again:"
  printf '%s\n' "$SETTINGS_ERROR"
  exit 1
fi

step "5. Language model (summaries and Q&A)"
llm_status
if [ "$LLM_PROVIDER" = "claude-code" ]; then
  # Default provider: the local Claude Code CLI with your own login; no API key.
  if [ "$LLM_READY" = "yes" ]; then
    ok "Using $LLM_LABEL with your Claude Code login (no API key needed)"
  else
    warn "${LLM_HINT:-Could not check Claude Code.} Search, library, and upload work without it."
  fi
elif [ "$LLM_PROVIDER" = "api" ] && credentials_found; then
  ok "Using the Anthropic API ($LLM_LABEL); credentials found"
elif [ "$LLM_PROVIDER" = "api" ]; then
  api_key=''
  if [ "$PROMPT" -eq 1 ]; then
    echo "  LLM_PROVIDER=api needs an Anthropic API key (https://console.anthropic.com/)."
    read -r -s -p "  Paste your key, or press Enter to skip: " api_key || api_key=''
    echo
  fi
  if [ -z "$api_key" ]; then
    warn "No API key set. Search, library, and upload work; to enable summaries and Q&A, set ANTHROPIC_API_KEY in .env, or use LLM_PROVIDER=claude-code."
  elif ! printf '%s' "$api_key" | grep -Eq '^[A-Za-z0-9_-]+$'; then
    warn "That doesn't look like an API key (expected letters, digits, - and _). Nothing was saved; edit .env by hand."
  else
    # python-dotenv (the library the app reads .env with) updates the existing
    # ANTHROPIC_API_KEY line in any form it accepts, or adds one. The key is
    # passed through the environment, never on a command line.
    NEW_API_KEY="$api_key" backend_python - "$ENV_FILE" <<'PY'
import os, sys
import dotenv
dotenv.set_key(sys.argv[1], "ANTHROPIC_API_KEY", os.environ["NEW_API_KEY"], quote_mode="never", follow_symlinks=True)
PY
    chmod 600 "$ENV_FILE"
    if credentials_found; then
      ok "Saved ANTHROPIC_API_KEY to .env (file readable only by you)"
    else
      fail "Could not save the key; set ANTHROPIC_API_KEY in .env by hand."
      exit 1
    fi
  fi
else
  warn "Could not determine the language model setup; check LLM_PROVIDER in .env."
fi

cat <<EOF

${BOLD}Setup complete.${RESET}

  Development (live reload):  make dev     then open http://localhost:5173
  Single server:              make start   then open http://localhost:8000

Without make, see "Running the App" in INSTALL.md.
EOF
