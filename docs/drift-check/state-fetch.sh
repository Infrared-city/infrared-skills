#!/usr/bin/env bash
# Fetch existing open drift-check issues + PRs from the skills repo as JSON.
# The output is fed into the LLM prompt so the model can dedup against
# already-tracked items.
#
# Usage::
#
#     ./state-fetch.sh [Infrared-city/infrared-skills] [drift-check]

set -euo pipefail

REPO="${1:-Infrared-city/infrared-skills}"
LABEL="${2:-drift-check}"

issues=$(gh issue list --repo "$REPO" --state open --label "$LABEL" \
  --json number,title,labels,body,createdAt --limit 100)
prs=$(gh pr list --repo "$REPO" --state open --label "$LABEL" \
  --json number,title,headRefName,body,createdAt --limit 100)

cat <<JSON
{
  "issues": $issues,
  "prs":    $prs
}
JSON
