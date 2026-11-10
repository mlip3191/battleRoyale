---
description: Turn a plain-English request into a well-scoped GitHub issue (or a few). Shows the full draft and creates nothing until you confirm.
argument-hint: "[what you want, in your own words]"
---

Help me file a well-scoped GitHub issue for Battle Royale. Follow `docs/issues.md` and TEAM_PROCESS Step 4. The forms in `.github/ISSUE_TEMPLATE/` define the sections.

What I want (may be empty): "$ARGUMENTS"

## 1. Interview (plain English, no jargon)
- If nothing was given, ask what I'd like changed or added.
- Ask only what you need, at most three short questions per message: who it's for and why, what "done" looks like, and anything it depends on. Look up the answers you can find yourself (`docs/plan/`, `docs/PRODUCT_SPEC.md`, `gh issue list --state open --limit 100`) instead of asking.
- If an open issue already covers it, show me that issue and ask whether to add a new one at all.

## 2. Pick the form
- **Feature** (`type: feature`): new behavior. Sections: User story ("As a ___, I want ___ so that ___"), Acceptance criteria, Likely files or areas, Out of scope, Depends on.
- **Bug** (`type: bug`): something broken. Sections: What happened, What should happen, Steps to reproduce, Screenshots, Acceptance criteria.
- **Chore** (`type: chore`): docs, process, setup, maintenance. Sections: What needs doing, Why, Acceptance criteria (done when).

Use those exact section names as `### ` headings in the body, in that order, so the issue matches the web form. If an optional section has nothing to say, keep its heading and write `_No response_` under it. Start the title with the form name, like the web forms do: `Feature: ...`, `Bug: ...`, or `Chore: ...`.

## 3. Write acceptance criteria
- Each one is a `- [ ]` checkbox that someone else can answer yes or no, with a concrete input and result (see the good-vs-weak table in `docs/issues.md`). Rewrite vague ones such as "works", "handles errors", or "is fast".
- Bugs always include "a test reproduces the bug and now passes".
- Never put keys, passwords, or course endpoint hosts in an issue.

## 4. Suggest labels
- One **type**: `type: feature`, `type: bug`, or `type: chore`.
- One **size**: `size: S` (a few hours) or `size: M` (about a day). If it is bigger than M, don't label it `size: L`; go to step 5.
- One **lane** if clear: `lane: mike`, `lane: adam`, `lane: gunnar`, `lane: felipe`, `lane: dillon` (owners and areas in `docs/plan/LANES.md`). If unclear, leave it off and say so.
- One **wave** if it fits the plan: `wave: 1` to `wave: 4`.
- Extras only when they apply: `status: blocked` (it depends on an open issue), `contract-change` (changes `backend/app/models/`, needs PM approval), `needs-pm` (needs a decision first), `good first issue`, `usability`, `accessibility`.
- Use only labels that exist (`gh label list --limit 100`). Never create labels.

## 5. Split anything bigger than M
If it is more than about a day of work, touches several lanes, or bundles unrelated changes, propose two or more issues of size S or M. Each one gets its own draft, labels, and criteria, and later ones say "Blocked by" earlier ones where needed. Show the split as a short numbered list first and ask whether I want it before drafting all of them.

## 6. Show the full draft and wait
Show each issue exactly as it will be created: title, labels, assignee (only if I named one), and the full body. Then ask: **"Create this issue? (yes / change something / cancel)"**. If there are several, ask once for the whole set and say how many will be created.
- **change something:** edit the draft and show it again.
- **cancel**, or anything other than a clear yes: create nothing and say "Cancelled — no issue was created."

## 7. Create it (only after a clear yes)
For each issue:
1. Tell me to expect two Approve prompts (one for saving the draft, one for creating the issue), then write the body to `.claude/tmp/new-issue-<short-name>.md`.
2. Run `gh issue create --title "<title>" --body-file .claude/tmp/new-issue-<short-name>.md --label "<label>"` (one `--label` per label, plus `--assignee <login>` only if I asked for one). For a split, create them in order and fill each "Blocked by #<n>" with the real number of the issue just created.
3. Report each new issue's number and link. Say that it lands in Backlog and the PM triages it (moves it to Ready).

Rules: one issue at a time; never start working on the issue, create a branch, or edit any other file. If `gh` fails, stop, explain in plain English, and propose a fix.
