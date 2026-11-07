---
description: List open PRs you can review, or review a specific PR (e.g. /review 42)
argument-hint: "[PR number]"
---

Use the review-prs skill (`.claude/skills/review-prs/SKILL.md`) and follow every step and rule in it.

PR number given: "$ARGUMENTS"

- If a PR number was given, skip the list in Step 1 and go straight to Step 2 for that PR.
- If nothing was given, start at Step 0 and show me what I can review.

Nothing is posted until I say send, and approval is always a separate question.
