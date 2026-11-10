#!/usr/bin/env bash
# Publish Mandate to GitHub.
#
#   ./scripts/publish.sh <github-username>
#
# Creates the repository with GitHub CLI when available and authenticated,
# otherwise pushes to an existing empty repo at
# https://github.com/<username>/mandate.
set -euo pipefail

REPO="mandate"
DESCRIPTION="Spend authority for autonomous agents — signed, scoped, revocable budgets settled through PayPal."

say() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

command -v git >/dev/null 2>&1 || die "git is not installed. Run: xcode-select --install"

cd "$(dirname "$0")/.."

OWNER="${1:-}"
if [ -z "$OWNER" ]; then
  OWNER="$(git config --global github.user 2>/dev/null || true)"
fi
[ -n "$OWNER" ] || die "usage: ./scripts/publish.sh <github-username>"

if [ ! -d .git ]; then
  say "• initializing repository"
  git init -b main >/dev/null
fi

if ! git config user.email >/dev/null 2>&1; then
  git config user.name "$OWNER"
  git config user.email "$OWNER@users.noreply.github.com"
  say "• local commit identity: $OWNER <$OWNER@users.noreply.github.com>"
fi

git add -A
if git diff --cached --quiet; then
  say "• nothing new to commit"
else
  git commit -m "Mandate: spend authority for autonomous agents" >/dev/null
  say "• committed"
fi

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  if gh repo view "$OWNER/$REPO" >/dev/null 2>&1; then
    say "• repository exists — pushing"
    git remote remove origin 2>/dev/null || true
    git remote add origin "https://github.com/$OWNER/$REPO.git"
    git push -u origin main
  else
    say "• creating public repository with GitHub CLI"
    gh repo create "$REPO" --public --source=. --remote=origin --push \
      --description "$DESCRIPTION"
  fi
  gh repo edit "$OWNER/$REPO" \
    --description "$DESCRIPTION" \
    --add-topic paypal \
    --add-topic ai-agents \
    --add-topic agentic-commerce \
    --add-topic fintech \
    --add-topic hackathon \
    --add-topic python >/dev/null 2>&1 || true
else
  say "• GitHub CLI not available — using git directly"
  say "  (create an empty public repo named '$REPO' on github.com first)"
  if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "https://github.com/$OWNER/$REPO.git"
  else
    git remote add origin "https://github.com/$OWNER/$REPO.git"
  fi
  git push -u origin main
fi

say ""
say "✓ https://github.com/$OWNER/$REPO"
say "  Verify the About sidebar shows: MIT license"
