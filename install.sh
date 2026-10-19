#!/bin/sh
# Install Max (max-cli) on macOS or Linux in one step.
#
#   curl -LsSf https://raw.githubusercontent.com/Abubakr-Alsheikh/max-cli/main/install.sh | sh
#
# Same script, for networks that block raw.githubusercontent.com:
#
#   curl -LsSf https://abubakr-alsheikh.github.io/max-cli/install.sh | sh
#
# It installs uv (a small installer for Python programs that brings its own
# Python) when it's missing, then Max with uv, puts both on your PATH, and
# checks that `max` answers. Run it again any time to update Max.

set -eu

say() { printf '\033[36m%s\033[0m\n' "$1"; }
warn() { printf '\033[33m%s\033[0m\n' "$1"; }

say "Installing Max..."

if ! command -v uv >/dev/null 2>&1; then
    say "Getting uv first (it installs Python for Max, too)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # uv puts itself in ~/.local/bin; new shells learn it from the profile uv
    # updated, this script now.
    PATH="$HOME/.local/bin:$PATH"
    export PATH
fi

# --upgrade installs Max, or updates the Max that's there.
if ! uv tool install --upgrade max-cli; then
    warn "uv could not install Max. Check your internet connection and run this line again."
    exit 1
fi

# Make `max` work in new shells (it changes the profile only when it must).
uv tool update-shell >/dev/null 2>&1 || true
PATH="$(uv tool dir --bin):$PATH"
export PATH

if ! max --version; then
    warn "Max is installed, but did not start. Open a new terminal and type: max doctor"
    exit 1
fi

printf '\n'
printf '\033[32m%s\033[0m\n' "Max is ready. Open a new terminal, then:"
say "  max          opens the dashboard"
say "  max doctor   checks your setup (FFmpeg, AI, YouTube)"
