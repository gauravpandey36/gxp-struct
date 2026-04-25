#!/usr/bin/env bash
# Publish GxP-Struct to GitHub.
#
# Usage:  bash scripts/publish.sh
#
# Environment variables (optional):
#   GH_USER     GitHub username (default: gauravpandey36)
#   GH_REPO     Repo name        (default: gxp-struct)
#   GH_VIS      "public" or "private" (default: public)

set -euo pipefail

GH_USER="${GH_USER:-gauravpandey36}"
GH_REPO="${GH_REPO:-gxp-struct}"
GH_VIS="${GH_VIS:-public}"

# Move to the project root regardless of where the script was invoked from.
cd "$(dirname "$0")/.."

echo "==> Project root: $(pwd)"

# 1. Smoke test — must pass before we publish anything.
echo "==> Running smoke test (rules-only, no API calls)"
if ! python3 validation_test.py --rules-only > /tmp/gxp_smoke.log 2>&1; then
    echo "Smoke test failed. Output:"
    cat /tmp/gxp_smoke.log
    exit 1
fi
tail -1 /tmp/gxp_smoke.log

# 2. Clean any half-initialized .git from a previous attempt.
if [ -d ".git" ]; then
    echo "==> Removing existing .git directory (previous attempt cleanup)"
    rm -rf .git || {
        echo "Could not remove .git. Pause OneDrive sync and retry."
        exit 1
    }
fi

# 3. Initialize, stage, commit.
echo "==> git init -b main"
git init -b main >/dev/null
git config user.email "chotupandey616@gmail.com"
git config user.name  "Gourav Pandey"

git add -A
STAGED=$(git status --short | wc -l | tr -d ' ')
echo "==> Staged ${STAGED} files"

git commit -m "GxP-Struct v0.1: machine-readable standard for pharmaceutical SOPs" \
           -m "- Schema specification for representing pharma SOPs in a machine-readable form (the \"Fourth Translation\")." \
           -m "- Reference implementation: deterministic rule engine + .gxp parser + RAG fallback + audit log." \
           -m "- Canonical example: examples/Deviation_SOP.gxp covering Deviation/CAPA, 23 rules across 8 tag families." \
           -m "- Golden Q&A suite: 10/10 passing on deterministic path with no API calls." \
           -m "- Designed against 21 CFR Part 11 / EU GMP Annex 11." \
           >/dev/null

COMMIT=$(git log --oneline -1)
echo "==> Committed: ${COMMIT}"

# 4. Push — prefer gh CLI, fall back to git.
if command -v gh >/dev/null 2>&1; then
    echo "==> gh CLI detected — creating repo and pushing in one step"
    gh repo create "${GH_USER}/${GH_REPO}" \
        --"${GH_VIS}" \
        --source=. \
        --remote=origin \
        --description "Open-source machine-readable standard for pharmaceutical SOPs — deterministic, auditable, GxP-aligned" \
        --push

    echo "==> Adding topics"
    gh repo edit "${GH_USER}/${GH_REPO}" \
        --add-topic pharmaceutical \
        --add-topic gxp \
        --add-topic rag \
        --add-topic 21-cfr-part-11 \
        --add-topic open-standard \
        --add-topic life-sciences \
        --add-topic deterministic-ai \
        --add-topic validated-state || echo "(topic add failed — add via web UI)"

    echo "==> Enabling Discussions"
    gh repo edit "${GH_USER}/${GH_REPO}" --enable-discussions || \
        echo "(discussions toggle failed — enable via web UI: Settings → General → Features)"
else
    echo "==> gh CLI not found — using git push directly"
    echo "    First, create the empty repo manually at:"
    echo "    https://github.com/new"
    echo "    Name: ${GH_REPO}, Visibility: ${GH_VIS}, leave README/license/.gitignore unticked."
    read -r -p "    Press Enter once the empty repo exists on GitHub..." _
    git remote add origin "https://github.com/${GH_USER}/${GH_REPO}.git"
    git push -u origin main
fi

echo ""
echo "==> Done."
echo "    Live URL:  https://github.com/${GH_USER}/${GH_REPO}"
echo "    Commit:    ${COMMIT}"
