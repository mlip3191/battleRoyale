---
name: review-prs
description: Use when a teammate asks what they can review, wants to see open pull requests, asks "what needs review?", types /review, or wants to review a specific PR. Lists open PRs and what each needs, runs an agent review that drafts detailed comments and proposed fixes, and posts nothing until the user confirms; approval is a separate, second confirmation.
---

# Review PRs

You help a teammate (often a non-coder) find a pull request to review and review it well. You draft; the human decides. **Never post anything to GitHub, and never approve, without the explicit confirmations described below.**

Speak in plain English. Explain any technical term the first time you use it.

## Step 0 — Preflight

Run these and stop with a plain-English fix if any fails:

```
gh auth status
gh repo view --json nameWithOwner --jq .nameWithOwner
gh api user --jq .login
git branch --show-current
git status --porcelain
```

Remember: `REPO` (owner/name), `ME` (login), `START_BRANCH`, and whether the working tree is clean.

## Step 1 — List open PRs and what each needs

```
gh pr list --state open --limit 50 --json number,title,author,isDraft,createdAt,updatedAt,additions,deletions,changedFiles,headRefName,headRepositoryOwner,reviewDecision,reviewRequests,latestReviews,statusCheckRollup,mergeable,labels,body,url
```

For each PR, work out:

- **Linked issue:** from `Closes #n` / `Fixes #n` in the body (say "none" if missing — that's a finding).
- **Size:** additions + deletions; flag over 300.
- **Checks:** from `statusCheckRollup` — required checks (CI, Secret scan, Critical files approval) all passed / some pending / some failed. Report the **AI QA Review** separately as advisory (its verdict from the bot's PR comment, or "not run").
- **Approvals:** count of `APPROVED` in `latestReviews`, and whether `ME` already reviewed (and on which commit).
- **Critical files:** `gh pr view <n> --json files --jq '.files[].path'`, compared with the paths in `.github/CODEOWNERS` (if it doesn't exist yet, use: CLAUDE.md, .claude/, .github/, .githooks/, .gitignore, .env.example, package.json, package-lock.json, backend/pyproject.toml, backend/uv.lock, backend/app/models/, docs/ARCHITECTURE.md).
- **From a fork?** `headRepositoryOwner` differs from the repo owner.

Then show **one table per group**, in this order, skipping empty groups:

1. **Needs your review** — not authored by `ME`, not draft, and either review requested from `ME` or fewer than 1 approval.
2. **Needs the PM** — touches critical files and the author isn't the PM; only the PM's approval satisfies the critical-files check (anyone can still review and comment).
3. **Blocked** — a failing required check or merge conflicts (`mergeable` = CONFLICTING). Reviewing is still useful; approving isn't yet. (A QA bot verdict alone never makes a PR blocked.)
4. **Approved, ready to merge** — the author should merge it.
5. **Your PRs** — authored by `ME`. You can't review these; show their status so you know what to fix.
6. **Drafts** — not ready; review only if the author asked.

Columns: `#`, title, author, linked issue, size (+/−), checks, QA bot, approvals, age, **what it needs** (one short phrase, e.g. "first review", "re-review after new commits", "PM approval for .github change", "fix failing tests first").

If there are no open PRs, say so and suggest picking up an issue from **Ready** on the project board.

Ask which PR to review (use the AskUserQuestion tool if available; offer the top 3 from "Needs your review" plus "Other"). If the user already gave a number (e.g. `/review 42`), skip straight to Step 2.

## Step 2 — Guards before reviewing

Stop and explain if any is true:

- **`ME` is the author.** "A different teammate has to review this — GitHub won't count your own approval."
- **Uncommitted work** (`git status --porcelain` not empty). Offer to commit or stash it first; don't touch it without a yes.
- **PR is from a fork / outside contributor.** Do a read-only review: **do not check out or run its code** on this machine (it could run anything). Say why.

Note but continue:

- Draft PR → review as comments only; no approval possible.
- `ME` reviewed before → this is a **re-review**: focus on commits since your last review (`git diff <last_reviewed_commit>..<head>` after fetching), and check whether your earlier comments were addressed.

## Step 3 — Agent review

Delegate to the **code-reviewer** subagent (`.claude/agents/code-reviewer.md`) with: the PR number, `REPO`, `ME`, `START_BRANCH`, whether it's a re-review (and the last reviewed commit), and whether running code is allowed (not for forks). If subagents aren't available, follow `.claude/agents/code-reviewer.md` yourself.

The agent returns:

1. **Report** (markdown, in the fixed format in the agent file).
2. **Inline comments** — a list of `{path, line, start_line?, severity: must-fix|nit|question, body}`. Every must-fix has a GitHub ```` ```suggestion ```` block with the exact fix when the fix fits in the changed lines; otherwise a clear description of the fix.
3. **Proposed additional fixes** — improvements beyond must-fix (missing tests, edge cases, docs, follow-ups), each marked *in this PR* or *follow-up issue*.
4. **Recommendation** — Ready to merge / Merge after fixes / Do not merge, with a one-line reason.
5. **Head commit SHA** the review applies to.

Make sure the agent switched back to `START_BRANCH` afterwards (`git branch --show-current`). If not, switch back and say so.

## Step 4 — Show the full draft, then ask before sending

Show the user **everything that would be posted**, exactly as it will appear: the report, then each inline comment with its file and line, then the proposed additional fixes.

**Secrets rule:** if the review found something that looks like a key or password, the comment must say where it is and what to do ("line 12 of config.py contains what looks like an API key — remove it and tell the PM so the key is replaced") and must **never repeat the value**. Check the draft for this before showing it.

Then ask (AskUserQuestion if available):

> **Send this review to PR #<n>?**
> - **Send as "Request changes"** — default when there are must-fix items
> - **Send as "Comment"** — default when there are none, or for drafts
> - **Edit first** — tell me what to change
> - **Cancel** — post nothing

- **Edit:** apply the user's edits, show the full draft again, and ask again. Loop until Send or Cancel.
- **Cancel:** post nothing, delete any temp file, and stop.
- Never offer "Approve" in this question. Approval is Step 6.

## Step 5 — Post the review (only after "Send")

1. Write the payload to `.claude/tmp/review-<n>.json` (create the folder; it is gitignored):

```json
{
  "commit_id": "<head SHA from step 3>",
  "event": "REQUEST_CHANGES",
  "body": "<the report, plus the proposed additional fixes section>",
  "comments": [
    { "path": "backend/app/intake/parser.py", "line": 42, "side": "RIGHT",
      "body": "**Must fix:** counts above 10,000 aren't clamped...\n\n```suggestion\n    count = min(count, settings.sim_max_count)\n```" }
  ]
}
```

   - `event` is `REQUEST_CHANGES` or `COMMENT`, as the user chose.
   - Inline comments must point at lines that are part of the diff (`side: RIGHT` for added/changed lines; use `start_line` + `line` for multi-line suggestions). Move any comment on a line outside the diff into the body under "Comments on unchanged code".
   - If the head commit changed since the review started (`gh pr view <n> --json headRefOid`), tell the user and offer to re-run Step 3 instead of posting a stale review.

2. Post it:

```
gh api repos/<REPO>/pulls/<n>/reviews --method POST --input .claude/tmp/review-<n>.json
```

3. If GitHub rejects an inline comment position, move those comments into the body and retry once. Then delete the temp file.
4. Show the review URL. GitHub notifies the author automatically; if they need a nudge, @mention them in a PR comment.

## Step 6 — Approval: a separate, second confirmation

Only consider approval if **all** are true; otherwise explain which one fails and stop:

- The review was just posted (Step 5).
- Recommendation is **Ready to merge** and there are **zero must-fix items**.
- All **required** checks have passed: CI, **Secret scan**, and **Critical files approval** (none failing or pending — except Critical files approval when `ME` is the PM, which this approval itself fixes; see below). The **AI QA Review** is advisory: mention its verdict, but it doesn't block.
- No merge conflicts; not a draft; `ME` is not the author.
- The reviewer actually ran or looked at the change (for UI changes, ask: "Did you try it in the running app?").

Then ask, as its own question:

> **Approve PR #<n> now?** Your approval lets <author> merge it into main.
> - **Approve**
> - **Not yet**

Only on **Approve**:

```
gh pr review <n> --approve --body "Approved after review (see my review above)."
```

If the PR touches critical files:
- `ME` isn't the PM: say "Mike's approval is still required by the critical-files check."
- `ME` is the PM (`mlip3191`): approvals don't re-trigger that check, so re-run it now. Find its run: `gh pr checks <n> --json name,link --jq '.[] | select(.name=="Critical files approval") | .link'`, take the number after `/runs/`, and (after a yes) run `gh run rerun <run id>`. Tell Mike it should turn green in about a minute.

## Step 7 — Follow-up issues (optional)

For each proposed additional fix marked *follow-up issue*, offer to create it. Show the full title, body (with "Found while reviewing #<n>"), and labels, and create it only after a yes:

```
gh issue create --title "<title>" --body "<body>" --label "type: chore"
```

## Step 8 — Wrap up

- Confirm you're back on `START_BRANCH` with the user's work untouched.
- Summarize in three lines: what you posted, the recommendation, and what the author should do next.

## Rules that never bend

- Nothing is posted without "Send". Nothing is approved without a separate "Approve".
- Never approve your own PR, a draft, a PR with failing or pending required checks, a PR with a must-fix item, or a PR containing a secret. The advisory QA bot never blocks approval on its own.
- Never run code from a fork or outside contributor.
- Never repeat a secret's value anywhere.
- Never push to, merge, or edit the PR's branch during a review. Suggestions go in comments; the author applies them.
