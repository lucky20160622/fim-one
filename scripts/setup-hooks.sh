#!/usr/bin/env bash
# Install git hooks for this repo.
# Run once after cloning: bash scripts/setup-hooks.sh

set -e

HOOKS_DIR="$(git rev-parse --show-toplevel)/.git/hooks"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

ln -sf "$SCRIPT_DIR/hooks/pre-commit" "$HOOKS_DIR/pre-commit"
chmod +x "$HOOKS_DIR/pre-commit"

echo "Git hooks installed"
